"""Tiny Persian / English translation layer."""
_LANG = "fa"

T = {
 "app": ("کتابخانه PDF حرفه‌ای", "PDF Library Pro"),
 "dashboard": ("داشبورد", "Dashboard"), "libraries": ("کتابخانه‌های من", "My Libraries"),
 "all_books": ("همه کتاب‌ها", "All Books"), "shelf": ("قفسه کتاب", "Bookshelf"),
 "recent": ("کتاب‌های اخیر", "Recent"), "reading": ("در حال مطالعه", "Reading"),
 "favorites": ("علاقه‌مندی‌ها", "Favorites"), "categories": ("دسته‌بندی‌ها", "Categories"),
 "authors": ("نویسندگان", "Authors"), "folders": ("پوشه‌های من", "My Folders"),
 "notes": ("یادداشت‌ها", "Notes"), "assistant": ("دستیار هوشمند", "AI Assistant"),
 "backup": ("پشتیبان‌گیری", "Backup"), "settings": ("تنظیمات", "Settings"),
 "add_books": ("افزودن کتاب", "Add books"), "add_folder": ("افزودن پوشه", "Add folder"),
 "search_ph": ("جستجو در عنوان، نویسنده و متن کتاب‌ها…", "Search titles, authors and book text…"),
 "sort": ("مرتب‌سازی", "Sort by"), "filters": ("فیلترها", "Filters"), "tags": ("برچسب‌ها", "Tags"),
 "grid": ("شبکه‌ای", "Grid"), "list": ("لیستی", "List"), "bookshelf": ("قفسه", "Shelf"),
 "books_count": ("%d کتاب", "%d books"), "you_have": ("%d کتاب در این کتابخانه دارید", "You have %d books"),
 "title": ("عنوان", "Title"), "author": ("نویسنده", "Author"), "translator": ("مترجم", "Translator"),
 "publisher": ("ناشر", "Publisher"), "category": ("دسته‌بندی", "Category"), "pages": ("صفحه", "pages"),
 "description": ("توضیحات", "Description"), "open": ("باز کردن", "Open"), "edit": ("ویرایش", "Edit"),
 "remove_from_lib": ("حذف از کتابخانه (فایل اصلی می‌ماند)", "Remove from library (keep file)"),
 "delete_file": ("حذف واقعی فایل از دیسک…", "Delete file from disk…"),
 "move_to_lib": ("انتقال به کتابخانه دیگر…", "Move to another library…"),
 "favorite": ("علاقه‌مندی", "Favorite"), "set_cover": ("انتخاب جلد دستی…", "Choose cover…"),
 "confirm": ("تأیید", "Confirm"), "cancel": ("انصراف", "Cancel"), "save": ("ذخیره", "Save"),
 "close": ("بستن", "Close"), "ok": ("باشه", "OK"), "yes": ("بله", "Yes"), "no": ("خیر", "No"),
 "added_n": ("%d کتاب اضافه شد", "%d books added"), "dups_n": ("%d تکراری", "%d duplicates"),
 "errors_n": ("%d خطا", "%d errors"), "indexing": ("در حال ایندکس متن…", "Indexing text…"),
 "new_library": ("کتابخانه جدید", "New library"), "lib_name": ("نام کتابخانه", "Library name"),
 "delete_lib": ("حذف کتابخانه", "Delete library"), "rename": ("تغییر نام", "Rename"),
 "color": ("رنگ", "Color"), "make_default": ("پیش‌فرض کن", "Make default"),
 "lock": ("قفل با رمز", "Set password"), "unlock": ("رمز کتابخانه", "Library password"),
 "wrong_pw": ("رمز اشتباه است", "Wrong password"), "location": ("مسیر ذخیره", "Storage path"),
 "bookmark": ("نشان‌گذاری", "Bookmark"), "highlight": ("هایلایت", "Highlight"),
 "add_note": ("افزودن یادداشت", "Add note"), "quote": ("ذخیره نقل‌قول", "Save quote"),
 "page": ("صفحه", "Page"), "zoom_in": ("بزرگ‌نمایی", "Zoom in"), "zoom_out": ("کوچک‌نمایی", "Zoom out"),
 "fit_width": ("عرض صفحه", "Fit width"), "fit_page": ("کل صفحه", "Fit page"),
 "rotate": ("چرخش", "Rotate"), "single": ("تک‌صفحه", "Single"), "double": ("دوصفحه", "Double"),
 "continuous": ("پیوسته", "Continuous"), "fullscreen": ("تمام‌صفحه", "Fullscreen"),
 "find": ("جستجو در کتاب", "Find in book"), "toc": ("فهرست", "Contents"),
 "password_req": ("این فایل رمزدار است. رمز را وارد کنید:", "This file is encrypted. Enter password:"),
 "open_failed": ("فایل باز نشد", "Could not open file"),
 "missing_file": ("فایل پیدا نشد", "File not found"), "relocate": ("بازیابی مسیر…", "Relocate…"),
 "theme": ("تم", "Theme"), "light": ("روشن", "Light"), "dark": ("تاریک", "Dark"),
 "accent": ("رنگ اصلی", "Accent color"), "language": ("زبان", "Language"),
 "ai_mode": ("حالت هوش مصنوعی", "AI mode"), "ai_none": ("بدون AI", "No AI"),
 "ai_local": ("محلی (Ollama)", "Local (Ollama)"), "ai_api": ("API (سرویس آنلاین)", "API (online)"),
 "ai_consent": ("متن‌های مرتبط PDF به سرویس آنلاین ارسال می‌شود. ادامه می‌دهید؟",
                "Relevant PDF text will be sent to the online service. Continue?"),
 "ai_not_found": ("این اطلاعات در متن PDF پیدا نشد.", "This information was not found in the PDF text."),
 "ask": ("بپرس", "Ask"), "run": ("اجرا", "Run"), "sources": ("منابع", "Sources"),
 "backup_now": ("پشتیبان‌گیری از کتابخانه فعلی", "Back up current library"),
 "backup_all": ("پشتیبان‌گیری کامل", "Full backup"),
 "restore": ("بازیابی (به‌صورت کتابخانه جدید)", "Restore (as new library)"),
 "last_backup": ("آخرین پشتیبان", "Last backup"), "never": ("هرگز", "Never"),
 "ocr_run": ("OCR صفحات بدون متن", "OCR pages without text"),
 "ocr_missing": ("Tesseract نصب نیست؛ OCR اختیاری است. راهنما: docs/OCR.md", "Tesseract not installed; OCR is optional. See docs/OCR.md"),
 "stats": ("آمار", "Statistics"), "total_pages": ("مجموع صفحات", "Total pages"),
 "done": ("انجام شد", "Done"), "error": ("خطا", "Error"), "progress": ("پیشرفت", "Progress"),
 "continue_reading": ("ادامه مطالعه", "Continue reading"), "no_books": ("کتابی وجود ندارد", "No books yet"),
 "drop_hint": ("فایل‌های PDF را اینجا رها کنید", "Drop PDF files here"),
 "new_shelf": ("قفسه جدید", "New shelf"), "shelf_name": ("نام قفسه", "Shelf name"),
 "shelf_style": ("ظاهر قفسه", "Shelf style"), "wood": ("چوبی", "Wood"), "modern": ("مدرن", "Modern"),
 "all": ("همه", "All"), "copy_mode": ("نحوه افزودن فایل", "How to add files"),
 "link": ("فقط پیوند به فایل", "Link only"), "copy": ("کپی در آرشیو داخلی", "Copy into archive"),
 "move": ("انتقال به آرشیو داخلی", "Move into archive"),
 "export": ("خروجی", "Export"), "clear": ("پاک کردن", "Clear"),
}


def set_lang(lang: str):
    global _LANG
    _LANG = "en" if lang == "en" else "fa"


def lang() -> str:
    return _LANG


def tr(key: str) -> str:
    v = T.get(key)
    if not v:
        return key
    return v[1] if _LANG == "en" else v[0]
