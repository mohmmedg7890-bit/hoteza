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


def birth_dates(value):
    from datetime import date
    from django.utils import timezone
    from hijridate import Gregorian
    try:
        birth=date.fromisoformat(str(value))
        if birth>timezone.localdate():raise ValueError()
        hijri=Gregorian.fromdate(birth).to_hijri().isoformat()
    except (ValueError,OverflowError):
        raise ValidationError('تاريخ الميلاد: اختر تاريخًا صحيحًا من 1924-08-01 حتى اليوم للتحويل بأم القرى.')
    return birth.isoformat(),hijri


def guest_profile(data):
    """Validate the registration form; never infer missing identity data for old guests."""
    result={}
    for key,label,required in [('first_name','الاسم الأول',True),('second_name','الاسم الثاني',False),('middle_name','الاسم الأوسط',False),('last_name','الاسم الأخير',True)]:
        value=' '.join(str(data.get(key,'')).split())
        if (required and not value) or len(value)>40 or (value and any(not (unicodedata.category(c)[0] in ['L','M'] or c in " '-’") for c in value)):
            raise ValidationError(label+': أدخل حروفًا صحيحة، بحد أقصى 40 حرفًا.')
        result[key]=value
        english=str(data.get(key+'_en','')).strip()
        if len(english)>80 or (english and not re.fullmatch(r"[A-Za-z '-]+",english)):raise ValidationError(label+': الاسم الإنجليزي بحروف إنجليزية فقط.')
        result[key+'_en']=english
    name=' '.join(result[k] for k in ['first_name','second_name','middle_name','last_name'] if result[k])
    fields=guest_fields({**data,'name':name})
    for key,choices,label in [('gender',['male','female'],'الجنس'),('customer_type',['citizen','resident','visitor'],'نوع العميل'),('id_type',['national_id','iqama','passport','gcc_id'],'نوع الهوية')]:
        value=str(data.get(key,''))
        if value not in choices:raise ValidationError(label+': اختر قيمة صحيحة.')
        result[key]=value
    for key,label,limit,required in [('nationality','الجنسية',80,True),('issuer_country','بلد الإصدار',80,False),('id_version','رقم النسخة',20,False),('vehicle_plate','لوحة المركبة',30,False),('workplace','مكان العمل',160,False),('work_phone','هاتف العمل',30,False)]:
        value=' '.join(str(data.get(key,'')).split())
        if len(value)>limit or (required and len(value)<2):raise ValidationError(label+': راجع القيمة المطلوبة.')
        result[key]=value
    classification=str(data.get('classification','regular'))
    if classification not in ['regular','vip','company']:raise ValidationError('تصنيف العميل غير صحيح.')
    result['classification']=classification
    identifier=str(data.get('id_number','')).translate(DIGITS).strip().upper()
    pattern={'national_id':r'1[0-9]{9}','iqama':r'2[0-9]{9}','passport':r'[A-Z0-9]{5,20}','gcc_id':r'[A-Z0-9]{5,20}'}[result['id_type']]
    if not re.fullmatch(pattern,identifier):raise ValidationError('رقم الهوية لا يطابق صيغة نوع الهوية المحدد.')
    result['id_number']=identifier
    result['birth_date'],result['birth_hijri']=birth_dates(data.get('birth_date',''))
    if data.get('birth_hijri') and data['birth_hijri']!=result['birth_hijri']:raise ValidationError('تاريخا الميلاد غير متطابقين؛ أعد اختيار التاريخ الميلادي.')
    return fields,result


def guest_photo(value):
    import base64,io
    from PIL import Image,ImageOps,UnidentifiedImageError
    if not isinstance(value,str) or not value.startswith('data:image/jpeg;base64,') or len(value)>280000:
        raise ValidationError('الصورة: ارفع صورة JPEG صالحة وحجمًا مناسبًا.')
    try:
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='JPEG' or im.width<400 or im.height<300 or im.width>2400 or im.height>2400:raise ValueError()
            im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((800,800))
            out=io.BytesIO();im.save(out,format='JPEG',quality=80)
            if out.tell()>200000:raise ValueError()
            return out.getvalue()
    except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombError):
        raise ValidationError('الصورة يجب أن تكون صالحة، بأبعاد 400×300 بكسل على الأقل.')
