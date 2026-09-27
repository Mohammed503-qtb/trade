# Task ID: 2-d — Agent: regime-builder

## المهمة
المهمة 2.4/2-d — مصنف نظام السوق (§9.3) + محرك انحياز HTF (§9.2) كحالتين موضعيتين حتميتين (بوابة خروج المرحلة 2: تتابعات حالات حتمية وموثقة؛ كل عتبة نسبية).

## الملفات (النطاق الحصري المطلوب)
- `engine/services/market_state/src/market_state/regime.py` — جديد (404 أسطر): RegimeFeatures/RegimeConfig/RegimeState/RegimeClassifier + REGIME_RULES_DOC.
- `engine/services/market_state/src/market_state/htf_bias.py` — جديد (289 سطرًا): HtfBiasInputs/HtfBiasConfig/HtfBiasState/HtfBiasEngine.
- `engine/services/market_state/src/market_state/__init__.py` — تعديل تصديري بسيط فقط (الواجهتان الجديدتان في `__all__`).
- `engine/tests/unit/test_regime.py` (484 سطرًا، 78 اختبارًا) و`engine/tests/unit/test_htf_bias.py` (364 سطرًا، 50 اختبارًا).

لم يُلمس أي شيء آخر (الوكيل الموازي على apps/replay — ملفات ablation.py/test_ablation.py له).

## القرارات التصميمية الموثقة
1. **فصل مسؤولية صارم**: المصنف/المحرك لا يحسبان سمات — المستدعي يملأ RegimeFeatures/HtfBiasInputs من features + VolatilityState ⇒ قابلية إعادة معزولة واختبار بقيم يدوية.
2. **hysteresis**: انتقال لا يثبت إلا بعد confirm_bars قراءة متتالية بنفس المرشح (3 نظام / 5 HTF)؛ قطع السلسلة يصفّر العد؛ transitions يحصي التأسيس الأول من UNKNOWN أيضًا.
3. **TRANSITION المموه (نظام)**: قاعدة 7 لا تثبت أبدًا — pending_count يتراكم إخباريًا والحالة المؤكدة تبقى (أنظمة §9.3 سلوكيات ملموسة والغموض ليس نظامًا).
4. **TRANSITION في HTF يثبت** (عدم تماثل موثق ومقصود): التذبذب الاتجاهي المتناوب (transition_flips=2 انعكاسات — حقل إضافي موثق) يفرض قراءة TRANSITION حتى يثبت بخمس متتاليات؛ التصفير عند تكرار اتجاهي متتالٍ وعند أي التزام.
5. **عتبات قرار**: atr_pct_mid مشتق ‎(low+high)/2‎ («mid-ish»)؛ volume_concentration_high يدخل قاعدة 2 كمؤكد توسع ثالث؛ gap_shock_atr=3.0 حقل إضافي موثق كنسبة ATR؛ normalized_range يُحمل ويشترك في بوابة النقص ولا يدخل الجدول (لا عتبة معلنة له).
6. **None ⇒ UNKNOWN للتحديث حصرًا** مع حفظ الحالة المؤكدة داخليًا وقطع سلسلة التأكيد؛ أشرطة None تُحصى في bars_seen (الدافئ أرضية إضافية بنفس دلالة VolatilityEngine: data_sufficient = bars_seen ≥ warmup_bars).
7. **HTF وكيل مرحلي**: §9.2 الكامل (تتابع بنيوي، بنية خارجية...) يأتي من مرحلة 3؛ HtfBiasInputs وحدها تحمل التغذية كي تُستبدل دون تغيير المستهلك؛ الكفاءة+الإشارة تقودان والوكلاء يغلقون بوابة الاكتمال فقط.

## البوابات (حرفيًا، من جذر engine بعد unset VIRTUAL_ENV)
- `ruff format --check services/market_state tests/unit/test_regime.py tests/unit/test_htf_bias.py` → `7 files already formatted`
- `ruff check <نفسها>` → `All checks passed!`
- `mypy` → `Success: no issues found in 80 source files`
- `pytest tests/unit/test_regime.py tests/unit/test_htf_bias.py -q` → `128 passed in 0.93s`
- `lint-imports` → `Contracts: 6 kept, 0 broken`
- المجموع الكلي: `863 passed, 13 deselected in 14.29s` (بلا انحدار — كان 735 قبل المهمة).

## الالتزام
`ef7316a` — feat(market-state): المهمة 2-d — مصنف النظام (§9.3) وانحياز HTF (§9.2) بحالات موضعية حتمية (5 ملفات، 1562 إدراجًا).
