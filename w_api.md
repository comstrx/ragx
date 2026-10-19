ال api: هو مشروع python + fastapi عبقرى مبنى خصيصا لبناء سيرفرات الويب عالية الاداء (حيث يتم استخدام احدث ممارسات fastapi و granian (فى المستقبل Graninan ولكن لسة ماقررتش)) لكى ابنى اقوى طبقة core تضاهى قوة لارافيل المرعبة فى السهولة والشمولية وسرعة fastapi والطلبات غير المتزامنة ومعاملات ال I/O الغير متزامنة,
════════════════════════════════════ 
١) إيه هو المشروع ده أصلاً؟ 
════════════════════════════════════ 
الـ API ده بـ Python 3.15 و FastAPI وبيتدار بـ uv، وكل حاجة عايشة تحت api/src/. بس خد بالك: ده مش "مشروع FastAPI عادي" فيه كام route وكام model. ده في الحقيقة فريمورك كامل مبني فوق FastAPI، فكرته إنه يبقى بنفس شمولية وسهولة Laravel بس في بايثون، مع أمان تام وأداء متقاس. 
 
الفكرة الجوهرية — وده أهم سطر في الكلام كله: 
  ▸ فيه طبقة اسمها core/ وهي "المحرك". كل حاجة تقنية في الدنيا بتحصل جواها وبس: أي مكتبة خارجية، أي كلام مع الشبكة، أي ملف على الديسك، أي عملية، أي قاعدة بيانات، أي broker، أي موديل AI. محدش غيرها يعرف إن SQLAlchemy موجودة أو httpx أو orjson أو obstore. مفيش نوع (type) من مكتبة خارجية بيعدّي من واجهة الكور للطبقات اللي فوقها. 
  ▸ وكل اللي فوق الكور (التطبيق نفسه) عبارة عن "تغليف رفيع جداً جداً" — thin wrappers. مفيش native logic فوق الكور. الكنترولر سطر أو اتنين، السيرفيس pipeline صغير بيركّب أفعال من الكور، الريبوزيتوري سلسلة Query، الموديل dataclass فاضي من السلوك. لو لقيت نفسك بتكتب loop أو regex أو try/except معقد أو بتستورد مكتبة في طبقة فوق الكور — ده معناه إن فيه فعل ناقص في الكور، تنزل تزوده هناك، مش تكتبه فوق. اسم القاعدة دي عندنا "الجاذبية": المنطق بينزل لأوطى طبقة تقدر تشيله. 
 
يعني بالبلدي: الكور هو الـ DSL العبقري الشامل لكل جانب حرفياً، والتطبيق مجرد إعلانات نضيفة بتقول "اعمل كذا" بأفعال الكور. 
 
════════════════════════════════════ 
٢) الرؤية والمبادئ 
════════════════════════════════════ 
  • شمولية Laravel: database/ORM/migrations، queue، events، schedule، cache، storage، mail، views، auth/token، validation، broadcasting/websocket، rate limiting، health، وكمان LLM adapters — كله موجود كدومينات في الكور ومش محتاج تجيب حاجة من بره. 
  • واجهة موحدة: نفس الأسماء بتتكرر في كل دومين (setup, ready, use, register, names, describe, dump, load, has, forget, clear, stats, close). لو عرفت دومين واحد هتعرف الباقي. 
  • خطأ واحد: كل فشل في النظام بيتحول لـ Fault(code, reason, message, errors) ومعاه enum اسمه Code فيه 13 كود (ok, created, accepted, bad_request, unauthorized, forbidden, not_found, method_not_allowed, conflict, validation, too_many_requests, internal, unavailable). مفيش exception خام بيطلع للعميل أبداً، ومفيش 500 بيتسرب بتفاصيله. 
  • typing موحد و return types موحدة: كل الدوال العامة متايبة بالكامل، mypy strict بيعدي بصفر أخطاء، والأنواع الموحدة جاية من الكور نفسه (DateTime, TimeDelta, UTC, Uuid, Path, Decimal, JsonValue). فوق الكور ممنوع تستورد datetime أو uuid أو pathlib أو json أو asyncio أو os أو re أو hashlib أو random أو time من الـ stdlib — فيه اختبار بيمنع ده. 
  • أمان بالتصميم: كل input من بره بيتفلتر على الحدود (pydantic/الـ Rulebook)، الأسرار بتتحجب في اللوج، المسارات محصورة (مفيش ..)، الرفع بيرفض امتدادات خطرة، الـ JWT وال argon2id والـ Fernet بدوران مفاتيح. 
  • الأداء بالقياس مش بالكلام: فيه benches بتطبع p50/p95/p99 وبتفشل لو الميزانية اتكسرت. 
 
════════════════════════════════════ 
٣) قوانين البنية (دي مش نصايح، دي اختبارات بتفشل لو كسرتها) 
════════════════════════════════════ 
  • اتجاه الاستيراد: core بيستورد core بس. config و app و database و routes بيستوردوا core و app بس. bootstrap هو الوحيد اللي بيستورد كله. 
  • دومينات الكور بتعتمد على بعض لتحت بس، ومفيش دورات (DAG) — فيه اختبار بيفحص ده بالـ AST. مثلاً storage بيبني على fs و net، و schedule بيبني على cache و queue، و queue بيبني على cache، بس مفيش حاجة بترجع لورا. 
  • كل دومين = فولدر فيه ملفات flat (مش nested) كل ملف ما بين 100 و300 سطر، مقسومين حسب المسؤولية، وبيتجمعوا في __init__.py بيصدّر __all__ وسينجلتون صغير بحرف صغير (fs, date, queue, llm...). الملف اللي يكبر بنطلع منه mixin أو helper class في ملف جديد. 
  • صفر تعليقات في الكود كله. الكود اللي محتاج تعليق معناه إن اسمه وحش — غيّر الاسم أو أعد الكتابة. ولا حتى # noqa أو # type: ignore؛ استثناءات اللينت بتتحط في pyproject.toml. 
  • أسلوب كتابة يدوي ثابت ومفيش formatter: تعريف الدالة بمسافة قبل القوس وجواه `def get ( self, key: str ) -> str:`، سطر فاضي بعد كل def/class له body أكتر من statement، الفروع القصيرة في سطر واحد، التعيينات المتتالية متراصّة على علامة =، الـ import: الخارجي والكور الأول، بعدين المحلي، بعدين سطر واحد للـ stdlib `import a, b`. ممنوع سطرين فاضيين متتاليين. 
  • ruff بـ select ALL و120 عمود، و mypy strict، و pytest على قاعدة بيانات حقيقية وبروكرز حقيقيين — مفيش mocks لحاجة ممكن تتشغل. 
 
════════════════════════════════════ 
٤) خريطة الكور — عشان تعرف تلاقي الفعل اللي محتاجه 
════════════════════════════════════ 
الطبقة السفلية (أدوات بحتة): 
  • error — Code و Fault و Faults (bad_request/not_found/... ). 
  • exception — Handler بيحوّل أي exception لـ Fault (maps, silent, levels)، وبيبلّغ اللي ≥500 بالـ traceback. 
  • log — structlog: setup/bind/share/span/debug..exception، بيربط request_id تلقائياً وبيحجب الأسرار. 
  • context — contextvars: request_id وخانات باسم (slot/get/set/bind/snapshot). مفيش state بيعيش بعد الريكوست. 
  • config — env بطبقات (.env ثم .env.<mode> ثم .secret والـ process بيكسب) و config.register/get بمفاتيح منقّطة، وكل دومين له class إعدادات بـ prefix (APP_ DB_ AUTH_ MAIL_ QUEUE_ EVENT_ CACHE_ SOCKET_ BROADCAST_ STORAGE_ ASSETS_ SCHEDULE_ DOCS_ LLM_ LOG_). 
  • json — orjson خلف واجهة واحدة + Walk (flatten/dig/merge/diff/prune) + Patch (JSON Pointer و JSON Patch و checksum و redact). 
  • parse — تحويل المدخلات الهشّة لأنواع: string/bool/integer/float/decimal/list/dict، وحدات (duration/bytes/rate/percent)، فحوص (is_int/is_json/is_uuid)، وأشكال نص (key_values, csv, ranges, semver, versions, mentions). 
  • string — Case/Inflect/Text/Codec/Probe/Template/Compare/Regex: slug, snake, plural, truncate, mask, base64, levenshtein, initials, regex sub/split, hash... 
  • number — رياضة وتنسيق وكلام: clamp/percent/median/percentile، human/bytes/ordinal/currency/roman، spell/spell_ordinal/is_prime/lerp/to_base. 
  • array — Collect/Dicts/Sets/Pager/Query: chunk/group/unique/pluck/key_by/where/first_where/sole/min_by/duplicates/transpose/tally/implode، وصفحات (Page). 
  • date — DateTime/TimeDelta/UTC + Moment (يفوق Carbon): add/sub/start_of/end_of/diff/human، Calendar (business days, next/previous weekday, nth_of_month, age, floor/round)، Duration، Period، Formatter بالتوكنات، وParser لغة طبيعية ("next friday", "in 3 days", "2 hours ago", "tomorrow at 3pm"). 
  • rand — uuid7 افتراضياً، token/otp/password/ulid/nanoid، weighted/dice/seeded، وFake للبيانات الوهمية (words, sentence, email على tlds محجوزة، ipv4, mac, amount). 
  • func — call/once/memo/pipe/compose/safe/retry/timeout/measure/debounce/throttle/single_flight/curry/juxt/after/before/load/discover. 
  • thread — gather(limit)/settle/map/first/timeout/retry/offload (threads)/compute (process pool)/poll، و pool (lanes)، و tasks (spawn/every/after/stop)، و shutdown signals. 
  • fast — الذاكرة المحلية السريعة: Lru، Ttl، Window/Sliding rate counters. الكاش والـ sessions بتبني عليها. 
  • fs — Path helpers، fs.file (قراءة/كتابة ذرية/chunks/checksum/mime/backup/times) مع Kind (نوع الملف)، fs.dir (walk/tree/size/prune) مع Scan (categorize/search/empty_dirs/disk_usage)، fs.archive (zip/tar/extract بحماية zip-slip)، fs.editor (تعديل سطور وملفات .env)، fs.watch (مراقبة)، والـ Driver protocol (put/get/stream/exists/size/modified/delete/copy/move/list/url/temporary_url/upload/download/remove/sync) بتنفيذين Local و S3، وسجل fs.drivers.use("name"). 
  • net — Client فوق httpx: request/get/post/stream/lines/sse/download/upload، retries، circuit breaker، hooks (on_before/on_after/on_error)، with_bearer/with_basic، pages() للـ pagination، Reply موحد، Url وIp وProbe (resolve/port_open/wait_port/free_port). 
  • crypto — argon2id للباسوردات، Fernet بدوران مفاتيح (seal/open/seal_file)، digests/HMAC، Keys و ApiKey. 
  • token — JWT (متماثل وغير متماثل، audience): issue/pair/verify/peek/bearer/api_key. 
  • validate — قواعد pydantic جاهزة (Email, Phone, Password, Slug, Url, ...) + Rulebook بأسلوب Laravel: validate.make(data, {"email": "required|email|max:254", "age": "integer|min:18"}) مع 40 قاعدة و required_if/with/without و bail ورسائل مخصصة. 
  • view — Jinja async: render(name, **data) مع shared globals و filters. 
  • mail — Message fluent (to/cc/bcc/about/with_html/attach) وtransports (smtp/log/memory). 
  • assets — ملفات المشروع العامة بروابط مختومة بالـ sha وcache immutable. 
 
طبقة اللايف سايكل: 
  • database — SQLAlchemy Core async على asyncpg خلف Adapter: Database (pool واحد، session للقراءة، transaction للكتابة)، ترجمة SQLSTATE لـ Fault، Blueprint/Schema (DSL للمايجريشن بدون SQL: id/string/json/enum/foreign/morphs/index/unique/gin/fulltext/check/...)، Migrator (apply/rollback/reset/fresh/status/make)، Model (frozen dataclass + relations: belongs_to/has_many/belongs_to_many/morph_*)، و Query[M] توليدي وimmutable: where/where_in/where_either/where_date/order_by/latest/limit/with_/with_trashed/get/first/sole/find/count/sum/avg/pluck/paginate/chunk/cursor/each/create/insert/upsert/update/increment/delete/restore/to_sql. حذف ناعم افتراضي، uuid7 مفاتيح. 
  • cache — Store protocol (memory فوق fast.Ttl أو redis): get/set/add/forever/remember/remember_forever/flexible(SWR)/pull/forget/many/increment/hit(rate)/lock (قفل موزّع بـ owner token)/tags. 
  • queue — Job/Failed/Queued، drivers (memory/sync/rabbitmq بقوائم quorum وتأخير بالـ dead-letter)، Workers (start/pause/resume/stop)، push/enqueue/push_unique/bulk/chain/batch، retries بـ backoff، Graveyard للفاشل (failed/retry_failed/flush_failed)، on_failure/on_success، drain للاختبارات. 
  • event — Event (registry + dump/load) و Events: listen/once/subscribe/on_any/off/dispatch/dispatch_if/dispatch_many/until/pause/resume/record/history؛ المستمع اللي بيرث Queued بيتنفذ في الكيو، غير كده inline؛ وBus محلي أو RabbitMQ عبر العمليات. 
  • schedule — Cron (5 حقول + أسماء + next/upcoming) و Task (every/hourly/daily_at/weekly_on/monthly_on/weekdays/on_days/between/last_day_of_month/timezone/without_overlapping/on_one_server/queued/when/skip/before/after/on_success/on_failure/pause/resume) و Schedule (call/job/tasks/find/pause/resume/due/run_due/run/upcoming/start/stop/status). تقدر تشوف كل المهام وتوقف أي واحدة وتشغلها يدوياً. 
  • socket — Frame/Connection/Hub/Socket: WebSocket hub بصناديق صادرة محدودة، ping وإغلاق صامت، حدود الإطار، presence channels، whisper، shedding للعميل البطيء، send_to_user/broadcast/kick/stats. 
  • broadcast — Channels بأنماط ("users.{user_id}") وتفويض (bool أو member dict للـ presence)، public/private/presence، emit/to(...).except_(...).send، relay تلقائي لأي Event معرّف channels()، و drivers محلي أو Redis pub/sub بين العمليات. 
  • http — App(FastAPI)، Route DSL (get/post/.../any/redirect/fallback/group/resource، .guarded/.limited/.named/.tagged/.constrained/.domain)، Router (url(name, **params))، Payload DSL واعي بالسياق (Incoming): all/input/only/except_/has/filled/boolean/integer/date/enum/file/bearer/ip/is_/route_is/validate/shape/require، Response (ok/created/page/fail/problem/json/text/html/redirect/file/download/stream/stream_download/sse/ndjson/with_cookie)، Sse/EventStream بنبضات keep-alive، Trace (request id + access log + nosniff)، Throttle ("60/minute" فوق cache.hit)، Docs (Scalar) وEnvelope موحد. 
  • health — Check/Result/Health: تسجيل probes بـ critical/tags/timeout وتقرير ok/degraded/down، وraء GET /health. 
  • llm — Provider protocol مع Local (أي خادم OpenAI-compatible بمسار قابل للضبط)، ChatGpt، DeepSeek، Claude، Gemini، كلهم تحت DSL واحد: llm.use("claude").system(...).temperature(0.2).max_tokens(800).json().attach(file).session(id).ask("...") أو .stream("...")، مع Message/Attachment/Options/Reply/Usage/Chunk و Sessions (استئناف بـ id، تاريخ، حساب توكنات). 
  • storage — أقراص (LocalDisk/S3Disk) هي نفسها drivers بتوع fs مسجلة كـ storage.<name>: put/put_dated/upload (بسياسة امتدادات وحجم)/fetch(url) عبر net/get/stream/exists/missing/append/prepend/files/directories/delete_directory/url/temporary_url/transfer. 
 
════════════════════════════════════ 
٥) الطبقات اللي فوق الكور (وكلها رفيعة لحد الخيال) 
════════════════════════════════════ 
سلسلة الطبقات: core → app/enums → config → app/utils/dna → app/utils/cycle (bases حاليا وهانغيرها ل cycleو نخليها توفر Controller, Repository يعنى بدل BaseController, BaseRepository ونفس التسمية تنطبق على الكل بدون base prefix) → models → repositories → services → controllers · middlewares · mails · jobs · events · listeners · exceptions → requests · resources → routes، وبيلزقهم bootstrap/. ملاحظة: كل فولدر تحت app/ اسمه جمع بحروف صغيرة. 
  • enums: المفردات الوحيدة للنظام، والسلوك متعلّق على الـ cases نفسها (label/render/...) بخرائط fail-closed. 
  • utils/dna: سلوك بيزنس صغير قابل لإعادة الاستخدام (identity parsing, passwords off the loop). utils/bases: الـ Base classes بمستوى وراثة واحد (BaseController, BaseService, BaseRepository, BaseModel-ish via Model, BaseRequest, BaseResource, BaseJob, BaseEvent, BaseListener, BaseMail). 
  • models: frozen dataclasses + relations + predicates صغيرة جداً. مفيش منطق. 
  • repositories: كل دالة سلسلة Query واحدة. 
  • services: pipeline رفيع بيستدعي repositories وأفعال الكور (token.issue, events.dispatch, storage.upload...). 
  • controllers: سطر أو اتنين: self.ok(await self._service.do(...)). 
  • requests: pydantic models بالقواعد الجاهزة من validate. resources: تشكيل الإخراج. 
  • jobs/events/listeners/mails: إعلانات فوق الـ bases؛ لو ورثت Queued بتروح الكيو، غير كده inline. 
  • routes: خرائط فقط — routes/api (Route DSL)، routes/channel (قنوات البث)، routes/events (event → listeners)، routes/schedule (المهام). 
  • bootstrap: Application (تسجيل الإعدادات، التوجيه، الـ wiring حسب driver keys)، Boot (lifespan: connect → migrate/seed ‖ openapi → warm → queue.start → events.start → broadcast.start → schedule.start، والإغلاق بالعكس)، وأوامر python -m bootstrap serve|migrate|rollback|status|seed|check|work|schedule|runbook. 
 
الغلاف الموحد لكل رد: data, message, errors, code, reason, meta.request_id (+ page/limit/total/pages مع الصفحات)، وهيدرز X-Request-Id و X-RateLimit-* و X-Content-Type-Options: nosniff. 
 
════════════════════════════════════ 
٦) إزاي تضيف حاجة من غير ما تكسر الفلسفة 
════════════════════════════════════ 
  • فعل ناقص؟ ضيفه في الدومين المناسب في الكور (ملف ≤300 سطر، mixin لو لزم)، واختبره، وسجّله في الواجهة. ممنوع كلمة منتج أو موديل أو مايجريشن جوه الكور. 
  • ميزة لايف سايكل؟ enum → migration بالـ DSL → model → repository → service → controller → request/resource → route → test → bench لو حرجة. كل طبقة سطر أو اتنين؛ أول ما طبقة تحتاج أكتر، انزل للكور. 
  • إعداد جديد؟ حقل بقيمة افتراضية في config/، ومتغيراته الضرورية في .env/.env.example، وفرع wiring في bootstrap، واختبار لو بيغير سلوك. 
  • مزوّد جديد (LLM/mail/storage/broker)؟ adapter في الكور خلف protocol، يتختار بـ driver key، له تنفيذ محلي/memory للاختبار وتنفيذ حقيقي بيتجرب على الخدمة الحقيقية. 
  • الاختبارات: ملفات flat قليلة وقاسية (laws, core, database, http, auth, storage, pipeline, realtime, lifecycle, llm) على قاعدة ragx_test حقيقية ولايف سبان حقيقي؛ الاختبار بيأكد قيم بالظبط ومسار الفشل (422 بالحقل، 401 بالكود، 429 بعد الحد). اختبار بيـ mock حاجة ممكن تتشغل بيتشال. 
  • البوابة قبل أي تسليم: uv run ruff check · uv run mypy · uv run pytest · uv run python -m bootstrap check. ومفيش commit ولا push غير بأمر صريح مني. 
 
════════════════════════════════════ 
٧) الخلاصة بالبلدي 
════════════════════════════════════ 
الكور هو كل حاجة: لغة كاملة (DSL) لكل جانب — ملفات، شبكة، تواريخ، نصوص، أرقام، تحقق، قاعدة بيانات، كاش، كيو، أحداث، جدولة، سوكِت، بث، توكنات، تشفير، لوج، صحة، وموديلات AI — بواجهة موحدة وخطأ واحد وتايبنج واحد وحدود أمان صارمة. والتطبيق فوقه مجرد "كلام نضيف": إعلانات قصيرة بتركّب أفعال الكور. لو اشتغلت على المشروع ده، شغلك إنك تحافظ على الفلسفة دي بالحرف: زوّد عبقرية الكور، وخلّي كل اللي فوقه رفيع، ومتكسرش قانون من قوانين الاختبارات الا لو هاتصلحه للاقسى او انك تعدله للاقوى، ومتقولش "خلصت" غير لما البوابة كلها خضرا. الكور يبقا فىdsl عبقىر مثل Path.xxx, File.xxx, Dir.xxx , Watch.xxx, Driver.use(Drivers::S3).upload|remove|download|sync وعاوزين نبنى طبقة string حقيقة وطبقة func حقيقية وطبقة date عبقرية للغاية وبتوفر date dsl اقوى من laravel carbon حرفيا, وهكذا لل array, number, rand كل دى طبقات لازم تبقا اقوى مايمكن وجاهزة على اعلى مستوى : انظر ايضا Turbox لكل هذه الدومينات , وايضا دومينات ال validate, parse, json, ودومين ال storage يعتمد بالكامل على core/fs, core/net وهكذا ,وبكدا افضل , يجب ان تكون دومينات اللايف سايلكل لتصل لاضعاف قوتها الحالية حرفيا باقصى شكل ممكن : database, cache, queue, schedule, event, fast (memory cache), log, error, socket, thread, config, crypto, token, broadcast , http, exception,  (اجبارى: فصل المسؤليات وتوحيد الاعتماديات واعتماد ال core domains على بعضهم بشرط عدم الاعتماديات بشكل عكسى ممنوع تماما) (اجبارى: تجزئة الدومين لاكثر من ملف وكل ملف يحتوى على 100 - 200 او 300 سطر بحيث كل دومين بيحتوى على ملفات بشكل flatt ولكن متنظمة ومفصولة حسب المسؤلية المحددة لكل ملف وبيتجمعو تحت __init__.py بالكامل مثل core/fs/{base, file, dir, path, watch, driver, _init_.py}) يمكنك اضافة اى دومين ناقص لاكمال الفجوة فى core/*** layer لتكون عبقرية للغاية ,  (اجبارى : كل الطبقات اللى اعلى core/ layer تبقا thin wrapper جدا جدا جدا بشكل يفوق الخيال تبقا Fun code جميل ومنظم وتحت هندلة اخطاء واحدة وtyping موحد و return types موحدة للغاية) , اكمل الفجوة المتبقية للوصول لنفس مستوى شمولية لارافيل فى اللايف سايكل , طور Route dsl ليكون عبقرى للغاية , طور ال request dsl ليكون يفوق الخيال و context aware وعبقرى جدا وبيوفر dsl عبقرى للتعامل مع payloads  طور core/http/response layer ايضا لتكون بشكل يفوق الخيال حرفيا وتتعامل مع SSE, Streaming, json, stirng وهكذا , لازم شمولية عبقرية , طور ال socket, queue, schedule, job, event dsls لان هذه الطبقات مهمة للغاية ولازم توفر تحكم كامل حرفيا ويقدر يجدول اى مهمة او اى حدث او توقفه او تشوف كل المهام والاحداث المجدولة والمستمعين وهكذا, طور دومين التعامل مع ال ai models حيث يوفر dsl عبقرى للتعامل مع الموديل سواء محلى او ريموتلى الافضل تخليه adaptor يعنى طبقة core/llm/{__init__.py, local.py وحتى المحلى يقدر يختار المسار من بره, chatgpt.py, claude.py, gemini.py, deepseek.py} والاهم ان كلهم بيخضعو ل dsl موحد حرفيا وكلهم بيوفر dsl عبقرى مش بس يسال او يبعتب برومبت بل ايضا يستقبل ملفات ويستقبل توكنات واعدادات للمحادثات وبدا محادثات جديدة او البدأ ب session id معين طبعا كل llm بيكون له طريقة تعامل ولكن فى النهاية كلهم تحت dsl موحد حرفيا , لازم فى النهاية نطلع بطبقة core/ تعتبر من اقوى الفريموركات فى عالم بايثون للويب حرفيا وتتضاهى قوة لارافيل المرعبة فى الشمولية والسهولة الشديدة والامان التام, طبعا مازال هناك فجوات ناقصة فى طبقة الكور ودومينات اخرى يجب اضافتها ليس بالكثير ولكن اعتقد اننا نريد اضافة 3 - 7 دومينات اخرى لتشمل كل الجوانب حرفيا فى ال programming lifecycle, webserver lifecycle بكل شئ حرفيا لنص لمستوى ابعد واقوى واشمل واسرع من لارافيل اخر اصدار حرفيا , كل شئ لازم يخضع تحت اختبارات قاسية جدا جدا جدا وليس بكثرة الاختباارت بل بالذكاء وعبقريتها , لازم طبقات ال tests, benches تبقا تحتها ملفات بشكل فلات وتغطى اختبارات طبقة الكور واختبارات اللايف سايكل ايضا , وايضا قياس سرعة الاداء والوصول لاقصى سرعة ممكنة , لازم نعمل استراتيجات مزامنة وتسريع جدا وتحسين لل bootstrap uptime ولازم نعمل استراتيجيات إحماء عبقرية للغاية لاحماء كل الاجزاء المهمة الداخلة فى اللايف سايكل , لازم core/func توفر طبقة عبقرية للتعامل مع الدوال سواء المتزامنة او الغير متزامنة سواء استدعاء callback او دالة صريحة وايضا كاش الدوال يجب ان توفر core/func dsl عبقرى للتعامل مع تكييش الدوال يعنى decorator مبنى فوق lru_cache h او لو وجد مكتبة احدث واقوى منها نستخدمها وايضا dsl عبقرى مبنى على functools , يجب ان نوفر قواعد جاهزة للتعامل مع التحقق فى core/validate وقواعد عبقرية جدا وشاملة (ودى مش هانعتبرها hard coded لانها تعتبر عامة ايضا) ولكن طبعا هذه القواعد تكون فى ملف مبنى على ال dsl نفسه الخام يعنى core/validate بتوفر dsl عبقرى للتحقق وشامل جدا ثم ملف بسيط او واجه فوقه لقوانين جاهزة , طبعا كل شئ فيه اكثر من مزود بيكون له adaptor مثل llm, domain, gateway, mail, sms, storage, broker , طبعا لازم نوفر دومينات ال core/{broker, fs, storage, domain, gateway, llm, mail, sms} حيث ان broker adaptor فوق rabbitmq and kafka and redpanda ولكن طبعا حاليا نعتمد rabbitmq فقط ولكن فى المستقبل لما نقرر نسويتش ل kafka or redpanda بالتاكيد المكان هايكون جاهز بمجرد اضافة ملف ليهم ونفس ال dsl هايكون زى ماهو وده هو عبقرية ال adaptor اللى لازم نوصل ليها حرفيا, وحيث ان storage فوق local, s3 وحيث ان mail فوق log, mailgun يعنى طريقتين , وحيث ان sms فوق whatsapp, telegram, sms وكلهم تحت dsl واحد مثل sms.send|prepare|to|from وهكذا , وياريت نوحد ال dsl بتاع الايميل وال sms مع انهم دومنين مختلفين ولكن الافضل نوحد ال dsl بتاعهم ليكون عبقرى وتجربة مستخدم اقوى, وحيث ان domain هو core/domain layer مبنى للتعامل مع الدومينات ومبنى فوق cloudflare, vercel ونفس ال dsl العبقرى جدا جدا وشامل للغاية للتعامل مع subdomains, domains, buy|register|set|get|delete|check|verify|exists وهكذا, وحيث ان طبقة ال core/gateway هى طبقة او دومين للتعامل مع بوابات الدفع ومبنى فوق paypal,stripe,paytabs,paymob حاليا ويوفر dsl موحد للغاية وطبعا نقدر نضيف اى طريقة دفع بمجرد اضافة ملف ليها , طبعا المفروض يوفر dsl عبقرى مثل withdraw|deposit|refund|webhook يعنى لازم يوفر dsl للتعامل مع السحب والايداع والتحويل والرفض والالغاء والاسترداد والويب هوكس ,وايضا يوفر dsl لهندلة الاخطاء وهكذا , وطبعا هو بيعمل normalize للبيانات اللى خارجه منه , يعنى هو بيعمل عقد موحد للبيانات اللى بتدخل وعقد موحد للبيانات اللى بتخرج , يعنى باختصر بياخد من المستخدم مفاتيح معينة باسماء موحدة مثل api_key, secret_key, form_id, client_id ومثل paylaod يكون موحد , والرد بيستقبله كل بوابة وكل ملف او كل بوابة بتوحد الرد الى رد متعارف عليه او payload response متعارف عليه , طبعا هنا من الذكاء اننا نبنى العقد بتاع الرد يكون شامل وفيه مفاتيح كتير ومفصلة كثل amount, total_amount, net_amount, gross_amount حتى ولو بوابة الدفع مش بتغطى ولكن علشان نعرف نغطى ده مع بوابات الدفع الى بتدعم ده , وبكدا طبقات اللى فوق الكور اصلا مش عارف ايه العقود بتاع paypal or stripe or.. اصلا يعنى كدا اقوى تجربة مستخدم عبقرية للغاية (اجبارى) وطبعا مفيش مانع او الافضل ايضا نعمل حقل او مفتاح فى ال reponse الموحد يكون فيه payload الخام اللى جاى من بوابة الدفع نفسها مثل response{raw: {}} يعنى كدا عندنا normalization response موحد وكثيف وعبقرى ومعانا raw item  فيه الرد الخام يعنى علشان لو الطبقات العليا قررت تخزنه فى قاعدة البيانات كمصدر اثبات فقط لا غير (ولكن اياك تعتمد انه ممكن يبص على ال raw اثناء اللوجيك), وبكدا وحدنا اعقد الدومينات المعقدة اللى بتقلق مهندسين الويب وهى ال : gateway, domain, sms, mail, broker, storage, llm, database, cache, event, queue, schedule,  http بشكل خيالى وغير مسبوق فى عالم الويب (وهنا التوحيد لازم يتم من غير انقاص اى ميزة للعمل الخام) , يعنى مش معنى اننا بنوحد وبنعمل normalization اننا نخسر اى مميزات خام موجودة بل نضيف مميزات موحدة (وده التحدى الحقيقى اننا نسعى للسهولة والتوحيد بدون فقد الاداء والامان وده هدف اجبارى), ولازم نوفر dsl عبقرى للغاية للتعامل مع views, config, env, asset كل دى حاجات لا تقل قيمة عن الاشياء الاخرى ولازم نخليها عبقرية جدا جدا وامنة للغاية , طبعا بالنسبة للطبقات الاعلى من ال core/ هى مش openianated structure بل احنا بنوفر dsl عبقرى والتكامل بتاع الطبقات او تقسيمة الطبقات بيتم التحكم فيها من خلال نقاط الدخول او نقاط الربط فى ال bootstra/ only (اجبارى) , بحيث اقدر اغير الهيكلية والمجلدات والطبقات والمسميات كلها حرفيا بدون تغيير اى حرف فى ال core/ واليك أمثلة عملية على الستايل والفورمات المطلوب اثناء كتابة اسطر الكود والملفات : from core.database import Blueprint, Schema
from app.enums import Table, TokenKind

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.morphs("owner")
            table.enum("kind", TokenKind, kind="token_kind")
            table.string("hash", 128).unique()
            table.timestamp("expires_at").index()
            table.timestamp("revoked_at").nullable()
            table.timestamps()

        await schema.create(Table.TOKENS, define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(Table.TOKENS)
 , from bootstrap import commands
import sys

if __name__ == "__main__":

    raise SystemExit(commands.run(sys.argv[1:]))
 , from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager

from core.broadcast import broadcast
from core.cache import cache
from core.database import Database, Migrator, Seeds, Status, adapters
from core.event import events
from core.llm import llm
from core.queue import queue
from core.schedule import schedule
from core.socket import socket
from core.fs import Path
from core.http import App, warm
from core.log import log
from core.thread import thread
from config import DatabaseConfig, QueueConfig, ScheduleConfig
from database.seeders import seeders

class Boot:

    def __init__ (
        self, source: Path, database: Database, settings: DatabaseConfig, application: str,
        jobs: QueueConfig | None = None, timetable: ScheduleConfig | None = None,
        paths: tuple[str, ...] = ("/health",),
    ) -> None:

        self._source      = source
        self._database    = database
        self._settings    = settings
        self._application = application
        self._jobs        = jobs or QueueConfig()
        self._timetable   = timetable or ScheduleConfig()
        self.paths        = paths

    @asynccontextmanager
    async def lifespan ( self, app: App ) -> AsyncGenerator[None]:

        with log.span("boot") as facts: await self.start(app, facts)

        try: yield
        finally: await self.stop()

    async def start ( self, app: App, facts: MutableMapping[str, object] ) -> None:

        await thread.gather(self.ready(), self.schema(app))

        facts["warmed"] = await self.warm(app)
        facts["pool"]   = self._database.describe()
        facts["queue"]  = self.work()
        facts["tasks"]  = self.clock()
        facts["events"] = events.bus().name

        if self._jobs.workers > 0: events.start()
        if broadcast.ready(): await broadcast.start()

    async def ready ( self ) -> None:

        with log.span("boot.database"):

            await self.connect()

            if self._settings.migrate: await self.migrate()
            if self._settings.seed: await self.seed()

    async def connect ( self ) -> None:

        cfg     = self._settings
        adapter = adapters.resolve(cfg.driver)
        url     = adapter.url(cfg.host, cfg.port, cfg.database, cfg.username, cfg.password)
        options = adapter.options(cfg.sslmode, cfg.search_path, self._application)

        await self._database.connect(adapter, url, cfg.pool_min, cfg.pool_max, cfg.timeout, options)

    def migrator ( self ) -> Migrator:

        return Migrator(self._database, self._source / "database" / "migrations")

    async def migrate ( self ) -> list[str]:

        return await self.migrator().apply()

    async def rollback ( self, steps: int = 1 ) -> list[str]:

        return await self.migrator().rollback(steps)

    async def status ( self ) -> Status:

        return await self.migrator().status()

    async def seed ( self ) -> list[str]:

        return await Seeds(self._database, seeders).run()

    async def schema ( self, app: App ) -> None:

        with log.span("boot.schema"): await thread.offload(app.openapi)

    async def warm ( self, app: App ) -> dict[str, int]:

        with log.span("boot.warm") as facts:

            statuses = await warm.paths(app, self.paths)

            facts.update(statuses)

        return statuses

    def work ( self ) -> int:

        queue.start(self._jobs.workers)

        return len(queue.names())

    def clock ( self ) -> int:

        if self._timetable.enabled: schedule.start(self._timetable.tick)

        return len(schedule.tasks())

    async def stop ( self ) -> None:

        with log.span("shutdown"):

            await schedule.stop()
            await socket.close_all()
            await broadcast.stop()
            await events.stop()
            await queue.close()
            await llm.close()
            await cache.close()
            await self._database.close()
 , from .app import Application
from .boot import Boot
from .commands import Commands
from .serve import Serve

application = Application().create
commands    = Commands()
serve       = Serve().run

__all__ = ["Application", "Boot", "Commands", "Serve", "application", "commands", "serve"]
 , وزى ماقولتلك لازم الملفات تبقا بشكل flatt ومسطحة داخل المجلدات الاتية : core/{domain-name}, app/{layer-name} عدا ال app/utils مقسمة الى app/utils/cycle and app/utils/dna , و database/{layer-name}, config/, bootstrap, public, views/{layer-name},routes/{api/, channel/, schedule/} , وزى ماقولنا كل الحاجات المهمة لها اعدادات فى config/ مثل database, queue, cache, event, mail, app, storage, broadcast, auth, schedule, docs, log, ولكن مفيش داعى لحاجات مثل llm, socket, assets, schedule لان اصلا llm dsl بياخد معلمات عادية , وال socket يندرج تحت broadcast وال assets تنتدرج تحت storage/ وال schedule يندرج تحت queue , يعنى عاوزين نعمل اعدادات مرنة ولكن عبقرية جدا وذكية مش ملفات مرصوصة جنب بعض وخلاص , وهانخلى ملف bootstrap/cli هو العبقرية القصوى فى اوامر ادارة المشروع مثل "serve", "migrate", "rollback", "status", "seed", "check", "work", "schedule", "runbook" طبعا مع اعتبار فلاجات مثل --force او تمرير معلمات وهكذا , وطبعا يكون له دالة بتعرض help عبقرى جدا ومنظم للغاية طبعا تقدر تعمل core/cli لتوفير Dsl عبقرى جدا يخلى ملف bootstra/cli مجرد thin wrapper لكتابة ال business logic بتاع الاوامر وحتى البزنس لوجيك بتاع الوامر نفسها يكون thin wrapper باستخدام ال dsl المتوفر لل database, cache, schedule, ... وطبعا لازم نعمل مجلد tests/ داخل ال src/ وده خاص باختبارات البزنس لوجيك زى بتاع لارافيل , اما الخارجى مثل tests, benches دول خاصين باختبارات الكور والحوكمة بتاع الهيكلية نفسها وقياس الاداء الكور والهيكلية , علشان لما نقرر فى المستقبل نفصل طبقة الكور بالكامل ف ى مشروع او مكتبة مستقلة ساعتها مانضطرش نفصل اى اختبارات او شئ , واعتقد اصلا لازم طبقة ال core/ توفر dsl للاختبارات زى مالارافيل بتوفر كدا , يعنى يكون عندنا core/test عبقرى جدا جدا ويوفر dsl عبقرى للغاية وشامل وبسيط جدا وسهل للغاية وشامل حرفيا كل ماهو مطلوب للاختبارات , وطبعا مفيش عندنا حوار unite, features والكلام الفارغ ده بل بنوفر dsl عبقرى للاختبار وخلاص علشان يقدر يعمل دوال اختبار بتنسيق وتنظيم موحد وعقود موحدة ويقدر يختبره نجاح response او مطابقة نتائج payload كاملة متوقعة او مطابقة نص فقط او كلمة فقط او رقم فقط او status فقط او code فقط , كل دى dsl بتوفرها core/test , هذه هى قصة api project والعبقرية اللى عملناها على مر الايام اللى فاتت ولازم نكملها ونطورها لتصل لاقصى مستوى من سرعة الاداء والامان التام فى الانتاج واقوى through put and latency فى عالم بايثون.
 