import assert from "node:assert/strict";

import { financialGrade } from "./rankingGrade";

assert.equal(financialGrade({ matrix_score: 85, net_income: 1000, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 70, net_income: 1000, category: "قلاع النمو والعوائد المتينة 🏰" }), "B");
assert.equal(financialGrade({ matrix_score: 55, net_income: 100, category: "شركات تشغيلية واعدة ومستقرة 📈" }), "C");
assert.equal(financialGrade({ matrix_score: 40, net_income: 10, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "D");
assert.equal(financialGrade({ matrix_score: 20, net_income: 10, category: "شركات ضعيفة النمو ⚠️لتجنبها" }), "D");
assert.equal(financialGrade({ matrix_score: -1000, net_income: -500, category: "الشركات الخاسرة وعالية المخاطر 🔴" }), "E");
assert.equal(financialGrade({ matrix_score: 90, net_income: -1, category: "قلاع النمو والعوائد المتينة 🏰" }), "E");
assert.equal(financialGrade({ matrix_score: 0, net_income: null, category: "تكرتشارت لحظي" }), null);
assert.equal(financialGrade({ matrix_score: 86, net_income: 1000, profit_growth: 12, debt_ratio: 0.08, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 90, net_income: 1000, profit_growth: 12, debt_ratio: 0.6, category: "قلاع النمو والعوائد المتينة 🏰" }), "D");
assert.equal(financialGrade({ matrix_score: 72, net_income: 400, profit_growth: -6, debt_ratio: 0.1, category: "شركات تشغيلية واعدة ومستقرة 📈" }), "C");
assert.equal(financialGrade({ symbol: "1120", matrix_score: 86, net_income: 1000, profit_growth: 12, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 0, net_income: 100, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 0, net_income: 100, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "C");
assert.equal(financialGrade({ matrix_score: 0, net_income: 10, category: "شركات ضعيفة النمو ⚠️لتجنبها" }), "D");
assert.equal(financialGrade({ matrix_score: -1000, net_income: 1000, category: "الشركات الخاسرة وعالية المخاطر 🔴" }), "D");
assert.equal(financialGrade({ matrix_score: 40, net_income: null, accumulated_loss_ratio: 0.5, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "E");
assert.equal(financialGrade({ matrix_score: 0, net_income: null, category: "تكرتشارت لحظي" }), null);

console.log("ranking grade checks passed");
