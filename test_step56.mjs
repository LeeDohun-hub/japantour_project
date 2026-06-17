/**
 * Step 5(예산) + Step 6(상세) 선택이 buildPrompt()에 실제로 반영되는지 테스트
 * 코드 수정 없이 브라우저 콘솔에서 직접 확인
 */
import { chromium } from 'playwright-core';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto('http://127.0.0.1:8000/', { waitUntil: 'networkidle' });
await page.waitForTimeout(800);

// ── wizardData를 직접 주입해서 buildPrompt 결과 확인 ──────────────
const result = await page.evaluate(() => {
  // Step 5 예산 데이터
  wizardData.budget = {
    currency: 'JPY',
    total: '300000',
    daily: '50000',
    priority: ['food', 'stay'],
    style: 'backpacker',
  };

  // Step 6 상세 데이터 (다양하게 선택)
  wizardData.additional = {
    companion: 'couple',
    pace: 'relaxed',
    travelStyles: ['healing', 'sns_hot'],
    foodPreferences: ['vegetarian', 'halal'],
    accessibility: true,
    sensitiveInfo: 'アレルギーあり（甲殻類）',
  };

  // 지역 / 활동 최소 데이터 (buildPrompt가 죽지 않도록)
  if (!wizardData.regions) wizardData.regions = ['seoul'];
  if (!wizardData.activities) wizardData.activities = ['food', 'cafe'];

  const prompt = buildPrompt(false);

  // 각 키워드가 프롬프트에 포함됐는지 체크
  const checks = {
    '예산 총액(30万円)':     prompt.includes('300,000') || prompt.includes('300000'),
    '일일예산(5万円)':       prompt.includes('50,000')  || prompt.includes('50000'),
    '食費重視(priority)':    prompt.includes('食費重視') || prompt.includes('food'),
    '宿泊費重視(priority)':  prompt.includes('宿泊費重視') || prompt.includes('stay'),
    'バックパッカー(style)': prompt.includes('バックパッカー') || prompt.includes('backpacker'),
    '同伴者:カップル':       prompt.includes('カップル') || prompt.includes('couple'),
    'ペース:ゆったり':       prompt.includes('ゆっくり') || prompt.includes('ゆったり') || prompt.includes('relaxed'),
    'スタイル:癒し':         prompt.includes('癒し') || prompt.includes('healing'),
    'スタイル:SNS人気':      prompt.includes('SNS') || prompt.includes('sns_hot'),
    '食事:ベジタリアン':     prompt.includes('ベジタリアン') || prompt.includes('vegetarian'),
    '食事:ハラール':         prompt.includes('ハラール') || prompt.includes('halal'),
    'アクセシビリティ':      prompt.includes('アクセシビリティ') || prompt.includes('accessibility') || prompt.includes('バリアフリー'),
    '特記事項(アレルギー)':  prompt.includes('アレルギー') || prompt.includes('甲殻類'),
  };

  const promptSnippet = prompt.slice(0, 4000); // 앞부분만 확인

  return { checks, promptSnippet };
});

console.log('\n=== Step 5/6 → buildPrompt() 반영 체크 ===\n');
let passCount = 0, failCount = 0;
for (const [key, ok] of Object.entries(result.checks)) {
  const mark = ok ? '✅' : '❌';
  if (ok) passCount++; else failCount++;
  console.log(`${mark} ${key}`);
}
console.log(`\n총 ${passCount + failCount}개 중 ✅ ${passCount} / ❌ ${failCount}`);

console.log('\n=== 프롬프트 앞부분 (4000자) ===\n');
console.log(result.promptSnippet);

await browser.close();
