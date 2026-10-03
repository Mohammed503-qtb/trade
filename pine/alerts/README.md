# ضبط تنبيه الويبهوك (§36 + D-07 + D-09)

## 1) إنشاء التنبيه على TradingView

1. افتح الرسم مع مؤشر `AMRE` (انظر `../README.md`).
2. Alert ← الشرط: `AMRE` ← «Any alert() function call».
3. الخيارات: **Once per bar close** (منطق مؤكد حصرًا §27.4 — لا تستخدم
   «Once per bar» أبدًا: ذاك متطور `DEVELOPING` لا يفوّض أمرًا).
4. رسالة التنبيه: اتركها فارغة — الحمولة يبنيها المؤشر بنفسه عبر
   `alert()` (جسم JSON خام بالحقول الثمانية §36).

## 2) رابط الويبهوك

```
https://<النطاق-العام>/api/tv/webhook?token=<TV_WEBHOOK_SECRET>
```

- **التوكن في معامل الاستعلام حصرًا** — TradingView لا يدعم ترويسات
  مخصصة، والجسم يحرم على الأسرار (§6.4/§37.1).
- `<TV_WEBHOOK_SECRET>` قيمة `TV_WEBHOOK_SECRET` في `engine/.env` —
  **لا تكتبها داخل شيفرة Pine أبدًا** ولا في أي جسم رسالة.
- المنفذان 80/443 فقط، وإقرار الخادم أسرع من 3 ثوانٍ (§6.4) — البوابة
  تقر فورًا وتعالج خلفيًا.

## 3) عقد الخدمة (الخطوات الثماني §36)

1. المصادقة على التوكن (رفض صحيح 401 عند غيابه/خطئه).
2. تحقق المخطط (رفض صحيح 422 للجسم الفاسد).
3. فحص تكرار مفتاح D-07
   `sha256(schema_version|source|alert_id|instrument|bar_time|event)`
   — يشتقه الخادم حصرًا؛ المكرر يُقر بلا معالجة ثانية.
4. حفظ التنبيه الخام في جدول `alerts` (§31.6).
5. إقرار فوري (< 3s).
6. نشر على NATS (`tv.alert.received`).
7. المحرك القانوني يعيد قراءة الحالة القانونية ويعيد التحقق.
8. حينها فقط تستمر المخاطرة — والتنفيذ الحي مؤجل للمرحلة 11 (MVP).

## 4) الحمولة (مرجع)

```json
{
  "schema_version": "1.0.0",
  "source": "tradingview",
  "alert_id": "BINANCE:BTCUSDT|1|LIQUIDITY_SWEEP_LOW|1735689600000",
  "instrument": "BINANCE:BTCUSDT",
  "bar_time_ms": 1735689600000,
  "timeframe": "1",
  "event": "LIQUIDITY_SWEEP_LOW",
  "price": 42000.5
}
```

- `alert_id` حتمي محليًا (أداة|إطار|حدث|زمن الشمعة) — نفس الشمعة تعطي
  نفس التنبيه دائمًا؛ ومفتاح D-07 فوقه يجعل التسليم كله idempotent.
- الأحداث المبثوثة: `LIQUIDITY_SWEEP_HIGH/LOW` · `BREAK_AND_ACCEPT_HIGH/LOW`
  · `EXTERNAL_BOS` · `INTERNAL_BOS` · `CHOCH`.
