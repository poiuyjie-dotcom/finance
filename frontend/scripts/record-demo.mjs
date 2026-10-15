import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const base = process.env.BASE_URL || "http://127.0.0.1:8013";
const root = process.env.DEMO_OUTPUT || "/tmp/alpharadar-demo";
await mkdir(root, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: root, size: { width: 1600, height: 900 } },
  reducedMotion: "reduce",
});
await context.addInitScript(() => {
  addEventListener("DOMContentLoaded", () => {
    const cursor = document.createElement("div");
    cursor.style.cssText = "position:fixed;width:18px;height:18px;border:2px solid #13836e;background:#13836e22;border-radius:50%;pointer-events:none;z-index:99999;left:-40px;top:-40px;transition:background .15s";
    document.body.append(cursor);
    addEventListener("mousemove", e => { cursor.style.left = `${e.clientX - 9}px`; cursor.style.top = `${e.clientY - 9}px`; });
    addEventListener("mousedown", () => { cursor.style.background = "#13836e99"; });
    addEventListener("mouseup", () => { cursor.style.background = "#13836e22"; });
  });
});
const page = await context.newPage();
page.setDefaultTimeout(60000);
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const began = Date.now();
const events = [];
async function mark(name) {
  const seconds = (Date.now() - began) / 1000;
  events.push({ seconds, name });
  console.log(`${seconds.toFixed(1)}s ${name}`);
}
async function until(seconds) {
  while (Date.now() - began < seconds * 1000) {
    await page.waitForTimeout(Math.min(1000, seconds * 1000 - (Date.now() - began)));
  }
}
async function click(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 18 });
  await page.waitForTimeout(250);
  await locator.click();
}
async function shot(name) {
  await page.screenshot({ path: `../screenshots/${name}.png`, fullPage: name !== "current-evidence" });
}
async function evaluate() {
  await click(page.getByRole("button", { name: "立即巡检", exact: true }));
  await page.getByRole("button", { name: "立即巡检", exact: true }).waitFor();
  await page.locator(".verdict").waitFor();
}
let taskId;
try {
  await page.goto(base);
  await page.locator(".task-table-row").first().waitFor();
  await mark("监控总览与状态筛选");
  await until(6);
  await click(page.getByRole("textbox", { name: "搜索监控任务" }));
  await page.getByRole("textbox", { name: "搜索监控任务" }).pressSequentially("宁德时代", { delay: 230 });
  await until(11);
  await page.getByRole("textbox", { name: "搜索监控任务" }).fill("");
  await until(15);
  await click(page.getByRole("link", { name: "新建监控", exact: true }).first());
  await mark("自然语言创建组合监控");
  await page.getByRole("textbox", { name: "监控关注点" }).pressSequentially("当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我", { delay: 90 });
  await until(24);
  await click(page.getByRole("button", { name: "生成监控规则", exact: true }));
  await page.getByRole("heading", { name: "检查监控规则" }).waitFor();
  await page.getByLabel("任务名称", { exact: true }).fill("宁德时代 · 价格、换手与公告联合监控");
  await mark("检查 AND / OR 条件与调度");
  await shot("current-create");
  await until(38);
  await page.getByRole("button", { name: "确认规则", exact: true }).scrollIntoViewIfNeeded();
  await until(43);
  await click(page.getByRole("button", { name: "确认规则", exact: true }));
  await until(48);
  await click(page.getByRole("button", { name: "启动监控", exact: true }));
  await page.waitForURL("**/task/*");
  taskId = page.url().split("/").pop();
  await mark("确定性巡检与逐条件归因");
  await evaluate();
  await until(65);
  await page.locator(".evidence-source").nth(1).scrollIntoViewIfNeeded();
  await until(69);
  await click(page.locator(".evidence-source").nth(1));
  await page.getByRole("dialog", { name: "原始证据" }).waitFor();
  await mark("原始字段、来源、单位和双时点证据");
  await shot("current-evidence");
  await until(82);
  await page.keyboard.press("Escape");
  await click(page.getByRole("button", { name: "编辑规则", exact: true }));
  await page.getByLabel("任务名称", { exact: true }).fill("宁德时代 · 联合监控（修订版）");
  await page.getByLabel("阈值 · 元", { exact: true }).fill("285");
  await until(91);
  await click(page.getByRole("button", { name: "保存为 v2", exact: true }));
  await click(page.getByRole("tab", { name: "版本变化", exact: true }));
  await page.getByRole("button", { name: "恢复此版本" }).waitFor();
  await mark("规则修订与版本差异");
  await shot("current-versions");
  await until(103);
  page.once("dialog", d => d.accept());
  await click(page.getByRole("button", { name: "恢复此版本" }));
  await until(109);
  await click(page.getByRole("tab", { name: "当前判定", exact: true }));
  await evaluate();
  await until(115);
  await page.goto(`${base}/validation`);
  await click(page.getByRole("button", { name: "启用所选模拟", exact: true }));
  await page.getByText("模拟已开启", { exact: true }).waitFor();
  await page.goto(`${base}/task/${taskId}`);
  await evaluate();
  await mark("数据过期：显式降级，不给出正常结论");
  await shot("current-stale");
  await until(132);
  await page.goto(`${base}/validation`);
  await click(page.getByRole("radio", { name: /双源价格冲突/ }));
  await click(page.getByRole("button", { name: "启用所选模拟", exact: true }));
  await page.getByText("模拟已开启", { exact: true }).waitFor();
  await page.goto(`${base}/task/${taskId}`);
  await evaluate();
  await mark("双源冲突：暂停判定并展示差异");
  await shot("current-conflict");
  await until(150);
  await page.goto(`${base}/validation`);
  await click(page.getByRole("button", { name: "恢复正常数据流", exact: true }));
  await page.getByText("正常数据流", { exact: true }).waitFor();
  await click(page.getByRole("button", { name: "检查输入", exact: true }));
  await page.getByText("已拦截投资建议诉求", { exact: true }).waitFor();
  await mark("合规边界：拦截投资建议");
  await shot("current-validation");
  await until(166);
  await page.goto(`${base}/task/${taskId}`);
  await evaluate();
  await click(page.getByRole("tab", { name: /^巡检记录/ }));
  await mark("恢复巡检与完整执行记录");
  await until(174);
  await page.goto(base);
  await page.locator(".task-table-row").first().waitFor();
  await mark("回到监控总览");
  await until(180);
  assert.deepEqual(errors, []);
} catch (error) {
  await page.screenshot({ path: `${root}/failure.png`, fullPage: true });
  throw error;
} finally {
  await page.request.post(`${base}/api/v1/simulator/fault-inject`, { data: { mode: "NORMAL" } });
  await writeFile(`${root}/chapters.json`, JSON.stringify(events, null, 2));
  await context.close();
  console.log(`VIDEO ${await page.video().path()}`);
  await browser.close();
}
