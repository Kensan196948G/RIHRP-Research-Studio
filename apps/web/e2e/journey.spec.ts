import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * 6 ステップ通し（研究仮説登録 → 報告書）の業務シナリオ検証。
 *
 * - シナリオごとに新しい研究プロジェクトを作り、最後に削除する。
 * - 各ステップの UI 表示だけでなく、サーバー側の保存内容（research_documents）と
 *   討論メッセージの形式（エージェント網羅・ラウンド・役割語彙・重複/欠落）を検査する。
 *   スコアは形式充足率であり、実LLMの推論品質・科学的妥当性の評価ではない。
 * - RIHRP_JOURNEY_ARTIFACT が設定されていれば、評価結果を JSON に書き出す
 *   （Standalone HTML 報告書の生成に使う）。
 */

const EMAIL = "admin@e2e.local";
const PASSWORD = "e2e-password-123";

type ResearchDoc = { version: number; payload: Record<string, unknown> };
type DebateMessage = { agent: string; round: number; kind?: string; text: string };
type StepResult = { name: string; ok: boolean; ms: number; detail?: string };
type DebateEval = {
  total: number;
  formatScore: number;
  agentCount: number;
  missingAgents: string[];
  rounds: number[];
  missingRounds: number[];
  emptyMessages: number;
  placeholderMessages: number;
  duplicateMessages: number;
  roleKeywordOk: string[];
  roleKeywordNg: string[];
  messageCount: number;
  perAgent: Record<string, number>;
  samples: { agent: string; round: number; text: string }[];
};
type JourneyResult = {
  key: string;
  title: string;
  hypothesis: string;
  projectId: string;
  startedAt: string;
  steps: StepResult[];
  debate?: DebateEval;
  counts: Record<string, number>;
  reportHeadings?: string[];
  exportName?: string;
  consoleErrors: string[];
  expectedHttpErrors: string[];
  failure?: string;
  cleanupError?: string;
  passed: boolean;
};

const results: JourneyResult[] = [];
const EXPECTED_AGENTS = ["fac", "lit", "evi", "met", "cri", "ide", "eth", "int"];
const ROLE_KEYWORDS: Record<string, RegExp> = {
  fac: /議題|論点|整理/,
  lit: /資料|文献|根拠/,
  evi: /信頼性|評価|裏付け/,
  met: /検証|測定|統制|計画/,
  cri: /弱点|反論|反証|保留/,
  ide: /提案|方向|可能性/,
  eth: /倫理|安全|データ|確認/,
  int: /評価|比較|点/,
};
const EXPECTED_ROUNDS = [1, 2, 3, 4];

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("メールアドレス").fill(EMAIL);
  await page.getByLabel("パスワード").fill(PASSWORD);
  await page.getByRole("button", { name: "サインイン", exact: true }).click();
  await expect(page.locator(".topbar")).toBeVisible();
}

async function openStudio(page: Page): Promise<void> {
  await login(page);
  await expect(page.locator("#nav .navitem")).toHaveCount(6);
}

async function saveStateText(page: Page): Promise<string> {
  return (await page.locator("#saveState").innerText()).trim();
}

async function csrfHeaders(page: Page): Promise<{ "X-CSRF-Token": string }> {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "rihrp_csrf")?.value;
  if (!csrf) throw new Error("CSRF cookie が見つかりません");
  return { "X-CSRF-Token": csrf };
}

async function getDoc(page: Page, id: string): Promise<ResearchDoc> {
  const response = await page.request.get(`/api/projects/${id}/research`);
  expect(response.ok(), `研究データの取得: HTTP ${response.status()}`).toBeTruthy();
  return (await response.json()) as ResearchDoc;
}

async function deleteProject(page: Page, id: string): Promise<void> {
  const res = await page.request.delete(`/api/projects/${id}`, { headers: await csrfHeaders(page) });
  expect(res.ok()).toBeTruthy();
}

async function waitForSaved(page: Page): Promise<void> {
  await expect
    .poll(async () => saveStateText(page), { timeout: 20_000 })
    .toBe("サーバーに自動保存済み");
}

async function createProject(
  page: Page, title: string, hypothesis: string, onCreated: (id: string) => void,
): Promise<string> {
  await openStudio(page);
  const previousId = await page.locator("#projSel").inputValue();
  await page.getByRole("button", { name: "＋ 新規研究" }).click();
  // 非同期に作成されるため、選択中 ID が変わり既定タイトルになるまで待つ。
  await expect
    .poll(async () => page.locator("#projSel").inputValue(), { timeout: 20_000 })
    .not.toBe(previousId);
  const id = await page.locator("#projSel").inputValue();
  expect(id).not.toBe("");
  onCreated(id);
  await expect(page.locator('input[data-bind="title"]')).toHaveValue("新しい研究テーマ");
  await page.locator('input[data-bind="title"]').fill(title);
  await page.locator('textarea[data-bind="hypothesis"]').fill(hypothesis);
  // デバウンス保存の完了をサーバー側の値で確認する（表示だけでは早すぎる）。
  await expect
    .poll(async () => {
      const doc = await getDoc(page, id);
      return `${doc.payload.title ?? ""}|${doc.payload.hypothesis ?? ""}`;
    }, { timeout: 20_000 })
    .toBe(`${title}|${hypothesis}`);
  return id;
}

async function runAllTasks(page: Page): Promise<void> {
  await page.locator('#nav .navitem[data-v="tasks"]').click();
  await page.selectOption("#speedSel", "4");
  const approvals: string[] = [];
  for (let i = 0; i < 90; i += 1) {
    const approve = page.getByRole("button", { name: "承認する" });
    if (await approve.isVisible().catch(() => false)) {
      const approvalKey = await approve.getAttribute("data-k");
      expect(approvalKey).not.toBeNull();
      approvals.push(approvalKey!);
      await approve.click();
      await page.waitForTimeout(500);
    }
    const run = page.getByRole("button", { name: "▶ 実行開始" });
    if (await run.isVisible().catch(() => false)) {
      await run.click();
    }
    await page.waitForTimeout(900);
    const stats = (await page.locator(".stats").innerText()).replace(/\s+/g, " ");
    if (stats.includes("100%") && stats.includes("10/10")) {
      expect(approvals).toEqual(["verify", "evaluate"]);
      return;
    }
  }
  throw new Error("タスクが 100% / 10/10 になりませんでした");
}

function evaluateDebate(messages: DebateMessage[]): DebateEval {
  const agents = new Set(messages.map((m) => m.agent));
  const rounds = [...new Set(messages.map((m) => m.round))].sort((a, b) => a - b);
  const missingAgents = EXPECTED_AGENTS.filter((a) => !agents.has(a));
  const missingRounds = EXPECTED_ROUNDS.filter((r) => !rounds.includes(r));
  const emptyMessages = messages.filter((m) => !m.text || m.text.trim().length < 15).length;
  const placeholderMessages = messages.filter((m) => /undefined|null|NaN|\[object/.test(m.text)).length;
  const duplicateMessages = messages.length - new Set(messages.map((m) => m.text)).size;
  const roleKeywordOk = EXPECTED_AGENTS.filter((agent) =>
    messages.some((m) => m.agent === agent && ROLE_KEYWORDS[agent].test(m.text)),
  );
  const roleKeywordNg = EXPECTED_AGENTS.filter((agent) => !roleKeywordOk.includes(agent));
  const perAgent: Record<string, number> = {};
  for (const agent of EXPECTED_AGENTS) {
    perAgent[agent] = messages.filter((m) => m.agent === agent).length;
  }
  const scoreParts = {
    agents: (EXPECTED_AGENTS.length - missingAgents.length) / EXPECTED_AGENTS.length,
    rounds: (EXPECTED_ROUNDS.length - missingRounds.length) / EXPECTED_ROUNDS.length,
    nonEmpty: messages.length ? 1 - emptyMessages / messages.length : 0,
    placeholders: messages.length ? 1 - placeholderMessages / messages.length : 0,
    role: roleKeywordOk.length / EXPECTED_AGENTS.length,
    unique: messages.length ? 1 - duplicateMessages / messages.length : 0,
  };
  const score = Math.round(
    30 * scoreParts.agents +
      20 * scoreParts.rounds +
      15 * scoreParts.nonEmpty +
      10 * scoreParts.placeholders +
      15 * scoreParts.role +
      10 * scoreParts.unique,
  );
  return {
    total: messages.length,
    formatScore: score,
    agentCount: agents.size,
    missingAgents,
    rounds,
    missingRounds,
    emptyMessages,
    placeholderMessages,
    duplicateMessages,
    roleKeywordOk,
    roleKeywordNg,
    messageCount: messages.length,
    perAgent,
    samples: messages.slice(0, 6).map((m) => ({ agent: m.agent, round: m.round, text: m.text.slice(0, 160) })),
  };
}

function collect(doc: ResearchDoc): Record<string, number> {
  const payload = doc.payload;
  return {
    evidence: ((payload.evidence as unknown[]) ?? []).length,
    critiques: ((payload.critiques as unknown[]) ?? []).length,
    candidates: ((payload.candidates as unknown[]) ?? []).length,
    revisions: ((payload.revisions as unknown[]) ?? []).length,
    tasksDone: ((payload.tasks as { status: string }[]) ?? []).filter((t) => t.status === "done").length,
  };
}

function writeResults(): void {
  const target = process.env.RIHRP_JOURNEY_ARTIFACT;
  // 失敗後の worker 再起動でも前のシナリオの証跡を失わない。
  // Playwright が実行開始時に初期化する outputDir を集計元にする。
  // 外部 target に前回の結果が残っていても取り込まない。
  const aggregate = path.join(test.info().project.outputDir, "journey-results.json");
  const previous = fs.existsSync(aggregate)
    ? (JSON.parse(fs.readFileSync(aggregate, "utf8")) as { results: JourneyResult[] }).results
    : [];
  const merged = new Map(previous.map((result) => [result.key, result]));
  for (const result of results) merged.set(result.key, result);
  const body = JSON.stringify({
    generatedAt: new Date().toISOString(),
    evaluation: "rule-based simulation format coverage; not scientific or LLM quality",
    results: [...merged.values()],
  }, null, 2);
  fs.mkdirSync(path.dirname(aggregate), { recursive: true });
  fs.writeFileSync(aggregate, body);
  if (target) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, body);
  }
}

// 集計先には実行ごとに新しいパスを指定する。各ケースの添付JSONが一次証跡。

async function runScenario(
  page: Page,
  key: string,
  title: string,
  hypothesis: string,
  kind: "standard" | "counter" | "revision",
): Promise<void> {
  const started = Date.now();
  const steps: StepResult[] = [];
  const errors: string[] = [];
  const expectedHttpErrors: string[] = [];
  let loggingIn = true;
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const url = message.location().url;
    const pathname = url ? new URL(url).pathname : "";
    // パスワード認証の未ログイン確認と、無効なAccess認証の応答だけを許容する。
    if (loggingIn && (
      (pathname === "/api/auth/me" && /status of 401/.test(message.text())) ||
      (pathname === "/api/auth/access" && /status of 404/.test(message.text()))
    )) {
      expectedHttpErrors.push(`${pathname}: ${message.text()}`);
    } else errors.push(`${url}: ${message.text()}`);
  });
  const result: JourneyResult = {
    key, title, hypothesis, projectId: "", startedAt: new Date(started).toISOString(),
    steps, counts: {}, consoleErrors: errors, expectedHttpErrors, passed: false,
  };
  let scenarioError: unknown;

  const step = async (name: string, fn: () => Promise<string | void>) => {
    const t0 = Date.now();
    try {
      const detail = await fn();
      steps.push({ name, ok: true, ms: Date.now() - t0, detail: detail || undefined });
    } catch (error) {
      steps.push({ name, ok: false, ms: Date.now() - t0, detail: String(error) });
      throw error;
    }
  };

  try {
    const id = await createProject(page, title, hypothesis, (createdId) => {
      result.projectId = createdId;
    });
    loggingIn = false;
    await step("01 研究仮説登録", async () => {
      await expect(page.locator("#nav .navitem").first().locator(".st")).toHaveText("r1 登録済み");
      await expect(page.locator("#liveCheck")).toContainText("構造スコア");
      if (kind === "revision") {
        await page.getByRole("button", { name: /改訂として記録/ }).click();
        await waitForSaved(page);
      }
      const doc = await getDoc(page, id);
      expect(doc.payload.hypothesis).toBe(hypothesis);
      return "r1 登録・ライブチェック表示・サーバー保存";
    });

    await step("02 AIタスク管理", async () => {
      await runAllTasks(page);
      await expect(page.locator(".stats")).toContainText("100%");
      await expect
        .poll(async () => {
          const doc = await getDoc(page, id);
          const tasks = (doc.payload.tasks as { status: string }[]) ?? [];
          return `${tasks.filter((t) => t.status === "done").length}/${tasks.length}`;
        }, { timeout: 30_000 })
        .toBe("10/10");
      const doc = await getDoc(page, id);
      for (const field of ["ethics", "critiques", "falsification"]) {
        expect(Array.isArray(doc.payload[field]), `工程成果: ${field}`).toBe(true);
        expect((doc.payload[field] as unknown[]).length).toBeGreaterThan(0);
      }
      const analysis = doc.payload.analysis as { iv: string; dv: string; nums: string[] };
      expect(analysis.iv.length).toBeGreaterThan(0);
      expect(analysis.dv.length).toBeGreaterThan(0);
      expect(analysis.nums.length).toBeGreaterThan(0);
      const plan = doc.payload.plan as { design: string; methods: unknown[]; measures: unknown[] };
      expect(plan.design.length).toBeGreaterThan(0);
      expect(plan.methods.length).toBeGreaterThan(0);
      expect(plan.measures.length).toBeGreaterThan(0);
      expect(doc.payload.reportAt).toEqual(expect.any(String));
      expect((doc.payload.reportAt as string).length).toBeGreaterThan(0);
      expect(JSON.stringify(doc.payload.logs ?? [])).not.toContain("[エラー]");
      return "10/10 完了（2種類の承認と工程成果を確認）";
    });

    await step("03 複数AI討論", async () => {
      await page.locator('#nav .navitem[data-v="debate"]').click();
      await expect(page.locator(".agents .agent")).toHaveCount(8);
      await page.getByRole("button", { name: /すべて表示/ }).click();
      await expect(page.locator("#debCnt")).toHaveText(/^(\d+)\/\1$/);
      let doc = await getDoc(page, id);
      let debate = evaluateDebate((doc.payload.debate as DebateMessage[]) ?? []);
      expect(debate.messageCount).toBeGreaterThan(0);
      expect(debate.missingAgents).toEqual([]);
      expect(debate.missingRounds).toEqual([]);
      expect(debate.formatScore).toBeGreaterThanOrEqual(90);

      if (kind === "counter") {
        // 反証資料を追加し、討論を再生成して評価が変わることを確認する。
        await page.locator('#nav .navitem[data-v="evidence"]').click();
        await expect(page.locator(".stats")).toContainText("資料数");
        const counterTitle = `${key} 反証用の追加資料`;
        await page.getByRole("button", { name: "＋ 手動で追加" }).click();
        await page.locator("#ae_title").fill(counterTitle);
        await page.locator("#ae_sum").fill("反証の立場で追加した検証用資料。");
        await page.locator("#ae_stance").selectOption("contradict");
        await page.getByRole("button", { name: "追加する" }).click();
        await expect
          .poll(async () => {
            const latest = await getDoc(page, id);
            const evidence = (latest.payload.evidence as { title: string; stance: string }[]) ?? [];
            return evidence.some((e) => e.title === counterTitle && e.stance === "contradict");
          }, { timeout: 20_000 })
          .toBe(true);
        const beforeTexts = ((await getDoc(page, id)).payload.debate as DebateMessage[])
          .map((m) => m.text)
          .join("\n");
        await page.locator('#nav .navitem[data-v="debate"]').click();
        await page.getByRole("button", { name: /討論を再生成/ }).click();
        // 再生成後の討論がサーバーへ保存されるまで待つ（本文の変化で確認）。
        await expect
          .poll(async () => {
            const latest = await getDoc(page, id);
            const messages = (latest.payload.debate as DebateMessage[]) ?? [];
            return messages.map((m) => m.text).join("\n") !== beforeTexts && messages.length > 0;
          }, { timeout: 20_000 })
          .toBe(true);
        doc = await getDoc(page, id);
        const regeneratedTexts = (doc.payload.debate as DebateMessage[]).map((m) => m.text).join("\n");
        expect(regeneratedTexts).not.toBe(beforeTexts);
        expect((doc.payload.debate as DebateMessage[]).some(
          (message) => message.agent === "lit" && message.text.includes(counterTitle),
        )).toBe(true);
        const regenerated = evaluateDebate((doc.payload.debate as DebateMessage[]) ?? []);
        expect(regenerated.missingAgents).toEqual([]);
        expect(regenerated.missingRounds).toEqual([]);
        expect(regenerated.formatScore).toBeGreaterThanOrEqual(90);
        debate = regenerated;
      }
      return `討論 ${debate.messageCount} 件・8 エージェント・4 ラウンド・形式充足率 ${debate.formatScore}点`;
    });

    await step("04 根拠・反証", async () => {
      await page.locator('#nav .navitem[data-v="evidence"]').click();
      await expect(page.locator(".stats")).toContainText("資料数");
      const before = await getDoc(page, id);
      const countBefore = ((before.payload.evidence as unknown[]) ?? []).length;
      await page.getByRole("button", { name: "＋ 手動で追加" }).click();
      await page.locator("#ae_title").fill(`${key} 検証用の追加資料`);
      await page.locator("#ae_sum").fill("通しシナリオで追加した検証用資料。");
      await page.getByRole("button", { name: "追加する" }).click();
      await expect(page.locator("#main")).toContainText(`${key} 検証用の追加資料`);
      await expect
        .poll(async () => {
          const doc = await getDoc(page, id);
          return ((doc.payload.evidence as unknown[]) ?? []).length;
        }, { timeout: 20_000 })
        .toBe(countBefore + 1);
      return `資料 ${countBefore + 1} 件（手動追加を含む）`;
    });

    await step("05 新仮説比較", async () => {
      await page.locator('#nav .navitem[data-v="compare"]').click();
      await expect(page.locator(".cand")).not.toHaveCount(0);
      await expect(page.locator("svg.radar")).toBeVisible();
      const rankBefore = await page.locator("#rank").innerText();
      await page.locator('input[data-w="novelty"]').evaluate((el: HTMLInputElement) => {
        el.value = "50";
        el.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await expect.poll(async () => page.locator("#rank").innerText(), { timeout: 10_000 }).not.toBe(rankBefore);
      // 先頭は主仮説カード（採択ボタンなし）なので、候補カードを対象にする。
      await page.locator(".cand:not(.main)").first().getByRole("button", { name: "採択" }).click();
      await expect
        .poll(async () => {
          const doc = await getDoc(page, id);
          const candidates = (doc.payload.candidates as { status: string }[]) ?? [];
          return candidates.some((c) => c.status === "採択");
        }, { timeout: 20_000 })
        .toBe(true);
      return "重み変更でランキング変動・候補を採択";
    });

    await step("06 研究報告書", async () => {
      await page.locator('#nav .navitem[data-v="report"]').click();
      await expect(page.locator("#reportBody h1")).toContainText(title);
      await expect(page.locator("#reportBody h2")).toHaveCount(11);
      result.reportHeadings = await page.locator("#reportBody h2").allTextContents();
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("button", { name: "HTMLで保存" }).click(),
      ]);
      const exportName = download.suggestedFilename();
      expect(exportName).toContain("RIHRP報告書");
      result.exportName = exportName;
      const exportPath = test.info().outputPath("research-report.html");
      await download.saveAs(exportPath);
      const exported = fs.readFileSync(exportPath, "utf8");
      expect(exported).toContain(title);
      for (const heading of result.reportHeadings) expect(exported).toContain(heading);
      expect(exported).toContain("科学的な真偽や新規性を保証しません");
      await test.info().attach("research-report", { path: exportPath, contentType: "text/html" });
      if (kind === "revision") {
        // 仮説を改訂し、再読込後も改訂履歴と最新仮説が残ることを確認する。
        await page.locator('#nav .navitem[data-v="register"]').click();
        const revised = `${hypothesis} 追加検証：季節変動の影響も評価する。`;
        await page.locator('textarea[data-bind="hypothesis"]').fill(revised);
        await page.getByRole("button", { name: /改訂として記録/ }).click();
        await waitForSaved(page);
        await page.reload();
        await expect(page.locator('textarea[data-bind="hypothesis"]')).toHaveValue(revised);
        const doc = await getDoc(page, id);
        expect(((doc.payload.revisions as unknown[]) ?? []).length).toBeGreaterThanOrEqual(2);
      }
      const doc = await getDoc(page, id);
      expect((doc.payload as { reportAt?: string }).reportAt).toBeTruthy();
      return `11 章・HTML 保存（${exportName}）`;
    });

    // 再読込してサーバー復元を確認
    await step("07 再読込・永続化", async () => {
      await page.reload();
      await expect(page.locator("#nav .navitem")).toHaveCount(6);
      await expect(page.locator("#projSel")).toHaveValue(id);
      const doc = await getDoc(page, id);
      expect(doc.version).toBeGreaterThan(0);
      return `version=${doc.version}・再読込後も同一プロジェクト`;
    });

    const doc = await getDoc(page, id);
    result.counts = collect(doc);
    result.debate = evaluateDebate((doc.payload.debate as DebateMessage[]) ?? []);
    expect(errors, "予期しないブラウザエラー").toEqual([]);
    result.passed = steps.length === 7 && steps.every((s) => s.ok);
  } catch (error) {
    scenarioError = error;
    result.failure = String(error);
  } finally {
    if (result.projectId) {
      try {
        // ページを離れて自動保存をflush/停止してから、作成したテーマのみ削除する。
        await page.goto("/healthz");
        await deleteProject(page, result.projectId);
      } catch (error) {
        result.cleanupError = String(error);
        scenarioError ??= error;
      }
    }
    if (errors.length && !scenarioError) {
      scenarioError = new Error(`予期しないブラウザエラー: ${errors.join("; ")}`);
      result.failure = String(scenarioError);
    }
    result.passed = result.passed && !scenarioError && errors.length === 0;
    results.push(result);
    writeResults();
    await test.info().attach("journey-result", {
      body: Buffer.from(JSON.stringify(result, null, 2)), contentType: "application/json",
    });
  }
  if (scenarioError) throw scenarioError;
}

test("J-A 標準シナリオ（河川・構造）", async ({ page }) => {
  await runScenario(
    page,
    "standard",
    "河道湾曲部における護岸基礎の洗掘対策（通し検証）",
    "河道湾曲部の外岸側で根固め工の重量を従来比1.5倍にすると、計画高水時の護岸基礎部の洗掘深は30%以上低減する。これは外岸近傍の流速が減衰し、河床材料の移動が抑制されるためである。",
    "standard",
  );
});

test("J-B 反証重視シナリオ（建設安全・倫理）", async ({ page }) => {
  await runScenario(
    page,
    "counter",
    "墜落制止用器具の支持点強度と衝撃荷重の低減（通し検証）",
    "墜落制止用器具の支持点強度を従来比1.2倍にすると、墜落時の最大衝撃荷重は20%以上低減する。これは支持点の変形が小さくなり、落下距離が短縮されるためである。",
    "counter",
  );
});

test("J-C 改訂・候補操作シナリオ（環境・データ）", async ({ page }) => {
  await runScenario(
    page,
    "revision",
    "河川流量観測における欠測補完手法の比較（通し検証）",
    "水位観測所の欠測を近隣観測所の水位から補完すると、流量推定誤差は15%以内に収まる。これは水位と流量の相関が高く、空間補間が有効なためである。",
    "revision",
  );
});
