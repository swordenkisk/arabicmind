# 🧠 عقل عربي — ArabicMind

<div align="center">

**محرك ثنائي LLM يُطلق الإمكانات الكاملة للذكاء الاصطناعي للمستخدمين العرب**

*A dual-LLM engine that unlocks 100% AI reasoning potential for Arabic speakers*

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)]()
[![Flask](https://img.shields.io/badge/Flask-2.x-green)]()
[![Tests](https://img.shields.io/badge/tests-20%2F20%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-brightgreen)]()
[![Arabic](https://img.shields.io/badge/language-العربية-gold)]()

**`github.com/swordenkisk/arabicmind` | swordenkisk 🇩🇿 | 2026**

</div>

---

## المشكلة | The Problem

عندما تسأل Claude/GPT/DeepSeek سؤالاً معقداً في البرمجة أو الرياضيات أو العلوم **باللغة العربية**، تكون الإجابة عادةً **أضعف** مما لو سألته بالإنجليزية.

هذه ليست مشكلة في الذكاء الاصطناعي — بل مشكلة **في البيانات**: معظم النماذج الكبيرة دُرِّبت أساساً على نصوص إنجليزية، وهو ما يُسمى **"ضعف النطق غير الإنجليزي"**.

*When you ask Claude/GPT/DeepSeek a complex question in Arabic, the answer is typically 15-40% weaker than the same question in English. ArabicMind solves this transparently.*

---

## الحل | The Solution

```
سؤالك بالعربية
      ↓
[نموذج الترجمة — سريع/رخيص]
      ↓
استعلام إنجليزي مُحسَّن (مع نظام بروبت متخصص)
      ↓
[نموذج الاستدلال — قوي]
      ↓
إجابة إنجليزية عميقة + سلسلة تفكير CoT
      ↓
[نموذج الترجمة — سريع/رخيص]
      ↓
إجابتك بالعربية الفصحى الدقيقة
```

**النتيجة:** تكتب بالعربية، يُفكّر النظام بالإنجليزية، يُجيبك بالعربية — بشفافية كاملة.

---

## المميزات | Features

### 🔄 المحرك الثنائي | Dual-LLM Engine
استخدم نموذجاً رخيصاً للترجمة ونموذجاً قوياً للاستدلال — **تحكم في التكلفة والجودة معاً**.

```
مثال: claude-haiku (ترجمة) + claude-opus (استدلال)
مثال: gpt-4o-mini (ترجمة) + deepseek-r1 (استدلال)
```

### 🖥 واجهة مزدوجة بجانبين | Dual-Pane Interface
- **الجانب الأيمن:** إجابتك بالعربية
- **الجانب الأيسر:** تفكير النموذج الخام بالإنجليزية

رؤية كاملة لما يفكر فيه النموذج — لا صندوق أسود.

### 🧠 توجيه ذكي تلقائي | Smart Domain Routing
**16 مجالاً متخصصاً** مع بروبتات احترافية مدمجة:

| المجال | Icon | الاستخدام |
|--------|------|-----------|
| تصحيح الأخطاء | 🐛 | debug code, fix bugs |
| كتابة الكود | 💻 | implement algorithms |
| البرهان الرياضي | 📐 | prove theorems |
| حل المسائل | 🔢 | calculus, algebra |
| الشرح العلمي | 🔬 | physics, chemistry |
| النحو العربي | 📚 | i'rab, sarf, balaghah |
| التفسير القرآني | 📖 | tafsir, ayah analysis |
| التاريخ الإسلامي | 🏛️ | dynasties, civilisation |
| الفقه | ⚖️ | madhabs, rulings |
| الطب | 🏥 | diagnosis, treatment |
| الفلسفة | 🤔 | logic, ethics |
| الاقتصاد | 💹 | Islamic finance |
| الأدب العربي | ✍️ | poetry, balaghah |
| الكتابة | 🖊️ | essays, reports |
| علم البيانات | 🤖 | ML, AI |
| عام | 💬 | everything else |

### 🔑 خصوصية مضمونة | Privacy Guaranteed
مفاتيح API مُخزَّنة في متصفحك فقط — **لا تمر بأي خادم خارجي أبداً**.

### 📊 سلسلة التفكير | Chain of Thought
عرض خطوات تفكير النموذج تلقائياً — يدعم:
- خطوات DeepSeek R1 (`<think>` tags)
- الخطوات المرقمة (1. 2. 3.)
- خطوات التفكير اللغوية (First/Then/Finally)

---

## التشغيل | Quick Start

```bash
git clone https://github.com/swordenkisk/arabicmind
cd arabicmind
pip install flask
python app.py
# افتح: http://127.0.0.1:7071
```

---

## هيكل المشروع | Architecture

```
arabicmind/
├── app.py                         ← Flask server (5 routes)
├── requirements.txt
│
├── src/
│   ├── engine/
│   │   └── dual_engine.py         ← Core dual-LLM pipeline
│   ├── providers/
│   │   └── base.py                ← Anthropic, OpenAI, DeepSeek, Gemini, Mock
│   └── prompts/
│       └── system_prompts.py      ← 16 domain prompts + router
│
├── templates/
│   └── index.html                 ← Arabic-first dual-pane UI
│
├── static/
│   ├── css/style.css              ← Dark Arabic UI (RTL + LTR)
│   └── js/app.js                  ← SSE streaming + markdown
│
└── tests/
    └── test_arabicmind.py         ← 20 tests (all passing)
```

---

## المزودون المدعومون | Supported Providers

| المزود | النماذج | الاستخدام المقترح |
|--------|---------|------------------|
| Anthropic Claude | opus-4-6, sonnet-4-6, haiku-4-5 | ترجمة: haiku / استدلال: opus |
| OpenAI | gpt-4o, gpt-4o-mini, o1 | ترجمة: mini / استدلال: 4o |
| DeepSeek | deepseek-reasoner, deepseek-chat | ممتاز للاستدلال الرياضي |
| Qwen / Tongyi | qwen-max, qwen-turbo | بديل اقتصادي ممتاز |
| Google Gemini | gemini-1.5-pro, gemini-2.0-flash | متعدد الوسائط |

---

## الاختبارات | Tests

```bash
python tests/test_arabicmind.py
# 20/20 اختباراً ناجحاً
```

---

## الترخيص | License

MIT — © 2026 swordenkisk 🇩🇿 — Tlemcen, Algeria

*"الذكاء الاصطناعي يجب أن يتحدث لغتنا بكامل قدراته."*
*"AI must speak our language at full capacity."*
