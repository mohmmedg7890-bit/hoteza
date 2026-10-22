"""Shared server rules for guest identity/contact and expected hotel times."""
import re,unicodedata
from datetime import time
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

DIGITS=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
def normalize_phone(value):
    s=re.sub(r'[\s()\-]','',str(value).translate(DIGITS))
    if re.fullmatch(r'05[0-9]{8}',s):return '+966'+s[1:]
    if re.fullmatch(r'\+9665[0-9]{8}',s):return s
    raise ValidationError('الجوال: أدخل 05xxxxxxxx أو +9665xxxxxxxx.')
def guest_fields(data):
    name=' '.join(str(data.get('name','')).split())
    words=name.split()
    if len(name)>160 or len(words)<2 or any(not any(unicodedata.category(c).startswith('L') for c in w) or any(not (unicodedata.category(c)[0] in ['L','M'] or c in "'-’") for c in w) for w in words):
        raise ValidationError('الاسم الكامل: أدخل اسمًا ثنائيًا على الأقل بحروف صحيحة.')
    phone=normalize_phone(data.get('phone',''))
    email=str(data.get('email','')).strip()
    if not email or len(email)>254:raise ValidationError('البريد الإلكتروني مطلوب بصيغة صحيحة.')
    validate_email(email)
    result={'name':name,'phone':phone,'email':email}
    for key,label,limit in [('region','المنطقة',100),('city','المدينة',100),('street','الشارع أو العنوان المختصر',300)]:
        value=' '.join(str(data.get(key,'')).split())
        if not 2<=len(value)<=limit:raise ValidationError(label+': أدخل تفاصيل العنوان المطلوبة.')
        result[key]=value
    return result

def expected_time(value):
    if not re.fullmatch(r'[0-2][0-9]:[0-5][0-9]',str(value)):
        raise ValidationError('الوقت مطلوب بصيغة ساعة ودقيقة صحيحة.')
    try:return time.fromisoformat(str(value))
    except ValueError:raise ValidationError('وقت غير صحيح.')
