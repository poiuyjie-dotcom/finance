import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";

const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const base = process.env.BASE_URL || "http://127.0.0.1:8011";
const output = process.env.SCREENSHOT_DIR || "/tmp/alpharadar-ui";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(90000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
let createdId;

async function noOverflow(label) {
  const widths = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    innerWidth,
  ]);
  assert.ok(widths[0] <= widths[1], `${label}: horizontal overflow ${widths}`);
}

try {
  await page.goto(base);
  await page.getByRole("heading", { name: "监控任务", exact: false }).waitFor();
  await page.locator(".task-table-row").first().waitFor();
  await noOverflow("desktop overview");
  await page.screenshot({
    path: `${output}/overview-desktop.png`,
    fullPage: true,
  });
  await page
    .getByRole("textbox", { name: "搜索监控任务" })
    .fill("不存在的任务XYZ");
  await page.getByRole("heading", { name: "没有匹配的任务" }).waitFor();
  await page.getByRole("button", { name: "清除筛选" }).click();

  await page.goto(`${base}/new`);
  await page
    .getByRole("textbox", { name: "监控关注点" })
    .fill("当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我");
  await page.getByRole("button", { name: "生成监控规则" }).click();
  await page.getByRole("heading", { name: "检查监控规则" }).waitFor();
  assert.equal(
    await page.locator(".condition-edit").count(),
    3,
    "all nested and root conditions are editable",
  );
  await page.getByLabel("任务名称", { exact: true }).fill("UI验收临时监控");
  await page.screenshot({ path: `${output}/create-rules.png`, fullPage: true });
  await page.getByRole("button", { name: "确认规则", exact: true }).click();
  await page.getByRole("button", { name: "启动监控", exact: true }).click();
  await page.waitForURL("**/task/*");
  createdId = page.url().split("/").pop();
  await page.getByRole("button", { name: "立即巡检", exact: true }).click();
  await page.locator(".verdict").waitFor();
  await page.locator(".evidence-source").first().click();
  await page.getByRole("dialog", { name: "原始证据" }).waitFor();
  await page.screenshot({ path: `${output}/evidence.png`, fullPage: true });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "编辑规则", exact: true }).click();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("UI验收临时监控已修改");
  await page.getByRole("button", { name: "保存为 v2" }).click();
  await page
    .getByRole("heading", { name: "UI验收临时监控已修改", exact: true })
    .waitFor();
  await page.getByRole("tab", { name: "版本变化" }).click();
  await page.getByRole("button", { name: "恢复此版本" }).waitFor();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "恢复此版本" }).click();
  await page
    .getByRole("heading", { name: "UI验收临时监控", exact: true })
    .waitFor();
  await page.getByRole("tab", { name: "当前判定" }).click();
  await noOverflow("desktop detail");
  await page.screenshot({
    path: `${output}/detail-desktop.png`,
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow("mobile detail");
  await page.screenshot({
    path: `${output}/detail-mobile.png`,
    fullPage: true,
  });
  await page.goto(base);
  await page.locator(".task-table-row").first().waitFor();
  await noOverflow("mobile overview");
  await page.screenshot({
    path: `${output}/overview-mobile.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "数据源与设置" }).last().click();
  await page.getByRole("heading", { name: "数据源与调度" }).waitFor();
  await noOverflow("mobile settings");
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.goto(`${base}/validation`);
  await page.getByRole("button", { name: "检查输入", exact: true }).click();
  await page.getByText("已拦截投资建议诉求", { exact: true }).waitFor();
  await noOverflow("mobile validation");
  await page.screenshot({
    path: `${output}/validation-mobile.png`,
    fullPage: true,
  });

  await page.goto(`${base}/task/${createdId}`);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除任务", exact: true }).click();
  await page.waitForURL(base + "/");
  createdId = null;
  assert.deepEqual(errors, [], "no browser runtime errors");
  console.log(
    "PASS: overview/search, nested rules, create, evaluate, evidence, edit, rollback, mobile layouts, settings, compliance, delete",
  );
  console.log(`Screenshots: ${output}`);
} finally {
  if (createdId) await page.request.delete(`${base}/api/v1/tasks/${createdId}`);
  await browser.close();
}
