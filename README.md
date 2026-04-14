# EMA Crossover Scanner

> סורק מניות עם Tradier API — גרסה v2.9

## 🚀 הרצה מקומית

```bash
# 1. כנס לתיקייה
cd ema-scanner

# 2. התקן dependencies
pip3 install -r requirements.txt

# 3. הרץ את השרת
python3 main.py

# 4. פתח בדפדפן
open http://localhost:8000
```

## ☁️ Deploy ל-Railway (גישה מכל מקום)

1. **העלה ל-GitHub:**
```bash
git init
git add .
git commit -m "EMA Scanner v2.9"
git remote add origin https://github.com/YOUR_USERNAME/ema-scanner.git
git push -u origin main
```

2. **Deploy ב-Railway:**
   - כנס ל-[railway.app](https://railway.app)
   - לחץ **New Project** → **Deploy from GitHub repo**
   - בחר את `ema-scanner`
   - Railway יזהה אוטומטית את ה-Python
   - לחץ **Deploy**

3. **קבל URL:** Railway ייתן לך URL כמו `ema-scanner.up.railway.app`
   - גישה מהטלפון, מהמחשב, מכל מקום

## 📁 מבנה

```
ema-scanner/
  main.py          ← FastAPI server
  database.py      ← SQLite storage
  requirements.txt ← Python packages
  Procfile         ← Railway config
  static/
    index.html     ← הממשק הגרפי
  data/
    scanner.db     ← נוצר אוטומטית
```

## 🔄 עדכון

```bash
git add .
git commit -m "update"
git push
```
Railway מעדכן אוטומטית תוך שניות.

## 📱 גישה מהטלפון

אחרי deploy ב-Railway — פתח את ה-URL בכל דפדפן מהטלפון.
המערכת מגיבה (responsive) למסכים קטנים.
