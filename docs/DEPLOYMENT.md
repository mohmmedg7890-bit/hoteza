# النشر على استضافة مستقلة

لم ينشر هذا الإصدار على نطاق عام. يلزم خادم Linux يدعم Docker Compose ونطاق موجه إلى الخادم. لا تكفي استضافة ملفات HTML ولا استضافة PHP المشتركة لتشغيل Django.

## تهيئة الخادم

1. اجلب المستودع إلى الخادم.
2. انسخ `.env.example` إلى `.env` واضبط النطاق وقائمة المضيفين وأصل CSRF.
3. أنشئ SECRET_KEY عشوائيًا عبر `python -c "import secrets; print(secrets.token_urlsafe(64))"`، وكلمة مرور قاعدة البيانات عبر `python -c "import secrets; print(secrets.token_hex(32))"`. خزّنهما في ملف البيئة فقط.
4. اضبط SMTP إذا أردت إرسال رسائل استعادة كلمة المرور. الحسابات التي تحتاج الاستعادة يجب أن تحمل بريدًا حقيقيًا مضبوطًا في إدارة الحساب.
5. افتح 80 و443 فقط للعامة. لا تعرض منفذ PostgreSQL أو منفذ التطبيق مباشرة.

```bash
docker compose build
docker compose up -d db
docker compose run --rm app python manage.py migrate
docker compose run --rm app python manage.py createcachetable
docker compose run --rm app python manage.py createsuperuser
docker compose run --rm app python manage.py check --deploy --fail-level WARNING
docker compose up -d
```

Caddy يصدر HTTPS تلقائيًا بعد صحة DNS والوصول للمنافذ. التطبيق لا يقبل كلمات سر افتراضية. `TRUST_PROXY=1` صالح هنا لأن منفذ التطبيق غير منشور ولا يستقبل إلا عبر الشبكة الداخلية؛ لا تضبطه خلف وسيط غير موثوق.

## التحقق قبل استقبال أي مستخدم

- افتح `/health/` عبر HTTPS.
- تحقق من نجاح CI على PostgreSQL لنفس commit المنشور.
- أنشئ منشأتين وحساب استقبال لكل واحدة واختبر منع الوصول المتبادل.
- جرّب الحجز والتحصيل والمغادرة والتصدير على الهاتف والكمبيوتر.
- اختبر رسائل البريد والتوقيت والفترات الضريبية وإعداداتها الفعلية.
- نفذ نسخة احتياطية واستعادة على قاعدة منفصلة قبل استخدام البيانات الحقيقية.
- راجع `RELEASE_GATES.md`؛ إعداد Docker وحده ليس اعتمادًا للبيع.

## النسخ الاحتياطي

نسخة منطقية كاملة عبر الخادم، وقد تحتوي على هويات الحسابات وكلمات المرور المجزأة؛ لا ترفعها إلى GitHub:

```bash
mkdir -p backups
chmod 700 backups
docker compose exec app python manage.py backup_data /tmp/hoteza-backup.json
docker compose cp app:/tmp/hoteza-backup.json backups/hoteza-backup.json
chmod 600 backups/hoteza-backup.json
docker compose exec app rm /tmp/hoteza-backup.json
```

غيّر اسم الملف لكل نسخة؛ الأمر يرفض الكتابة فوق نسخة موجودة. جدولة النسخ والاحتفاظ بنسخ مشفرة خارج الخادم مسؤولية التشغيل ولم تُفعّل على استضافة في هذه الجلسة. كذلك يوصى بنسخ PostgreSQL الأصلية عند اعتماد الإنتاج.

## الاستعادة

جهّز قاعدة منفصلة فارغة، نفّذ `migrate` و`createcachetable` ثم:

```bash
python manage.py restore_data /secure/path/backup.json --confirm-empty-database
```

الأمر يرفض قاعدة تحتوي مستخدمين أو منشآت. لا تختبر الاستعادة فوق قاعدة العميل.

## التحديث والتراجع

خذ نسخة قبل أي تحديث. ثبت commit محددًا، ابنِ الصورة، راجع migrations ثم نفذها واختبر الصحة والدورة الأساسية. لا ترجع كودًا قديمًا على مخطط قاعدة غير متوافق؛ استعد النسخة في قاعدة منفصلة عند الحاجة. لا تستخدم `seed_demo` أو `flush` على قاعدة حقيقية.
