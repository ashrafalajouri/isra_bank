import sqlite3
from datetime import datetime

DB = 'app.db'
subject_name = 'بايثون'

questions = [
    # Chapter 5
    ("في بايثون، الثوابت الخاصة بالقوائم List تكون محاطة بـ:", ["{}", "()", "[]", "<>"], "C", "Lists are surrounded by square brackets []"),
    ("أي عبارة صحيحة عن Tuples؟", ["يمكن تعديل عناصرها بعد الإنشاء", "غير مرتبة لكنها قابلة للتغيير", "لا يمكن تعديل عناصرها بعد الإنشاء", "تبدأ الفهارس من 1"], "C", "Tuples are immutable like strings"),
    ("ناتج list(range(6)) هو:", ["[1,2,3,4,5,6]", "[0,1,2,3,4,5]", "[0,1,2,3,4,5,6]", "[6]"], "B", "range(6) generates 0..5"),
    ("ناتج list(range(6,10)) هو:", ["[6,7,8,9]", "[6,7,8,9,10]", "[7,8,9,10]", "[6,10]"], "A", "range(6,10) returns 6..9"),
    ("ناتج list(range(7,21,3)) هو:", ["[7,10,13,16,19]", "[7,11,15,19]", "[7,10,13,16,19,22]", "[7,9,11,13,15,17,19]"], "A", "Step of 3 from 7 to <21"),
    ("دالة len() في بايثون تعيد:", ["قيمة آخر عنصر", "عدد العناصر", "أول عنصر", "نوع الكائن"], "B", "len returns number of items"),
    ("إذا كان a=[1,2,3] و b=[4,5,6] فإن a+b يساوي:", ["[1,2,3,4,5,6]", "[4,5,6,1,2,3]", "[1,2,3]", "خطأ"], "A", "List concatenation"),
    ("الأمر t.sort() يقوم بـ:", ["إرجاع نسخة مرتبة", "ترتيب القائمة تصاعديًا في مكانها", "ترتيب تنازلي فقط", "حذف العناصر"], "B", "sort sorts list in place"),
    ("إذا كان t=[9,41,12,3,74,15] فإن t[1:3] يعيد:", ["[9,41,12]", "[41,12]", "[12,3]", "[41,12,3]"], "B", "Slice 1:3"),
    ("العبارة t[-1::-1] تعطي:", ["نسخة مرتبة", "القائمة بالعكس", "أول عنصر فقط", "آخر عنصر فقط"], "B", "Reverse order slicing"),
    ("نوع الكائن الناتج عن zip(year_list, pl_list) هو:", ["list", "tuple", "zip", "dict"], "C", "type(x) is <class 'zip'>"),
    ("وظيفة enumerate مع قائمة لغات تعطي:", ["العناصر فقط", "الفهارس فقط", "أزواج (index, element)", "قيمة عشوائية"], "C", "enumerate returns index and item"),

    # Chapter 6
    ("أي وصف يطابق Set في بايثون؟", ["مرتبة وقابلة للتكرار", "غير مرتبة وغير قابلة للتكرار", "مرتبة وقابلة للتغيير", "مفهرسة تبدأ من 1"], "B", "Sets are unordered and no duplicates"),
    ("لإنشاء Set فارغة نستخدم:", ["{}", "[]", "set()", "()"], "C", "empty set = set()"),
    ("عملية الاتحاد بين مجموعتين يمكن كتابتها بـ:", ["&", "|", "-", "%"], "B", "Union uses |"),
    ("عملية التقاطع بين مجموعتين يمكن كتابتها بـ:", ["|", "-", "&", "+"], "C", "Intersection uses &"),
    ("عملية الفرق بين مجموعتين يمكن كتابتها بـ:", ["-", "&", "|", "/"], "A", "Difference uses -"),
    ("أي عبارة صحيحة عن remove و discard في set؟", ["remove لا يحذف", "discard يسبب خطأ إذا لم يوجد عنصر", "remove يسبب خطأ إذا لم يوجد عنصر", "لا فرق بينهما"], "C", "remove raises error if not found; discard does not"),
    ("القواميس Dictionaries هي:", ["قوائم مرتبة", "مجموعة قيم بدون مفاتيح", "أزواج مفتاح/قيمة", "نصوص فقط"], "C", "Key/Value pairs"),
    ("للتكرار على مفاتيح وقيم القاموس نستخدم:", ["items()", "values() فقط", "keys() فقط", "zip()"], "A", "for key, value in dict.items()"),
    ("في المثال: print('CS' in depts) حيث depts={'IT':101,'CIS':102,'MC':103} ستكون النتيجة:", ["True", "False", "None", "Error"], "B", "CS not in depts"),
    ("الدالة pop في القاموس:", ["تحذف كل العناصر", "تعيد القيمة وتحذف المفتاح", "تضيف مفتاح", "ترتب القاموس"], "B", "pop returns value"),

    # Chapter 7
    ("رمز *args يُستخدم لـ:", ["تمرير قاموس", "تمرير عدد غير معروف من الوسائط", "تعريف متغير ثابت", "استدعاء دالة"], "B", "Arbitrary arguments"),
    ("رمز **kwargs يُستخدم لـ:", ["تمرير عدد غير معروف من الوسائط المسماة", "تمرير قائمة", "تمرير tuple", "إغلاق برنامج"], "A", "Arbitrary keyword arguments"),
    ("تعريف lambda في بايثون يكون:", ["lambda arguments : expression", "lambda = arguments", "def lambda():", "lambda =>"], "A", "Lambda syntax"),
    ("عند انتهاء عناصر الـ iterator يتم رفع:", ["ValueError", "StopIteration", "TypeError", "IndexError"], "B", "StopIteration"),
    ("الميزة الأساسية للـ generator هي استخدام:", ["return", "yield", "break", "continue"], "B", "Generators use yield"),
    ("الجملة assert x<=60 ستقوم بـ:", ["طباعة x", "تتجاهل الشرط", "رفع خطأ إذا الشرط False", "تحويل x إلى int"], "C", "assert raises when false"),
    ("تحويل 'Hello Bob' إلى int سينتج:", ["0", "ValueError", "TypeError", "نجاح"], "B", "invalid literal for int"),

    # Chapter 8
    ("الفرق الأساسي بين re.match و re.search هو:", ["لا فرق", "match يبحث في كل النص", "match يتحقق فقط من بداية النص", "search يتحقق فقط من البداية"], "C", "match at beginning"),
    ("الـ Raw String يُكتب مثل:", ["'pattern'", "r'pattern'", "u'pattern'", "b'pattern'"], "B", "r'...'"),
    ("الرمز \\d في Regular Expressions يعني:", ["أي حرف", "Digit 0-9", "Whitespace", "Not Digit"], "B", "digit"),
    ("فتح ملف للقراءة الافتراضية يكون بالوضع:", ["w", "a", "r", "x"], "C", "r read default"),
    ("الوضع b في فتح الملفات يعني:", ["Text mode", "Binary mode", "Backup", "Begin"], "B", "binary"),

    # Chapter 9
    ("الدالة __init__ في الكلاس تُسمّى:", ["المدمر Destructor", "المنشئ Constructor", "المقارن", "المنسّق"], "B", "constructor"),
    ("المتغيرات ذات الشرط __name في الكلاس تدل على:", ["وراثة", "إخفاء بيانات", "فرز", "تكرار"], "B", "data hiding with double underscore"),
    ("الدالة __str__ تُستخدم عند:", ["عمليات الجمع", "الطباعة أو str()", "المقارنة", "الحذف"], "B", "print uses __str__"),
    ("وراثة كلاس في بايثون تتم بكتابة:", ["class A: B", "class B extends A", "class B(A):", "class B <- A"], "C", "class Manager(Employee)"),

    # Chapter 10
    ("في Tkinter، الدالة Tk() تقوم بـ:", ["فتح ملف", "إنشاء نافذة رئيسية", "إنهاء التطبيق", "تشغيل thread"], "B", "Tk() creates main window"),
    ("في زر Tkinter، الخاصية command تأخذ:", ["استدعاء الدالة مباشرة", "اسم الدالة بدون أقواس", "نص زر", "عدد"], "B", "function name"),
    ("لإدخال نص متعدد الأسطر في Tkinter نستخدم:", ["Entry", "Label", "Text", "Button"], "C", "Text widget"),
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# fix mojibake subject name if exists
cur.execute("UPDATE subjects SET name=? WHERE name LIKE '??????'", (subject_name,))

# ensure subject
cur.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,))
row = cur.fetchone()
if row:
    subject_id = row[0]
else:
    cur.execute("INSERT INTO subjects (name, created_at) VALUES (?, ?)", (subject_name, datetime.utcnow().isoformat()))
    subject_id = cur.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,)).fetchone()[0]

# remove old AI questions for this subject
cur.execute("DELETE FROM questions WHERE subject_id = ? AND source = 'ai'", (subject_id,))

now = datetime.utcnow().isoformat()

for i, (qtext, choices, correct, expl) in enumerate(questions, start=1):
    exam_type = 'mid' if i % 2 == 0 else 'final'
    choice_a, choice_b, choice_c, choice_d = choices
    cur.execute(
        """
        INSERT INTO questions (subject_id, exam_type, question_text, choice_a, choice_b, choice_c, choice_d, correct_choice, image_path, source, explanation, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (subject_id, exam_type, qtext, choice_a, choice_b, choice_c, choice_d, correct, None, "ai", expl, now, now)
    )

conn.commit()
conn.close()
print(f"Inserted {len(questions)} AI questions for subject '{subject_name}'.")
