# Build instalatoare – Soft Ofertare & Admin

Un singur folder care contine tot ce trebuie: **cele doua exe**, **imaginile** (logo + icon) si **cele doua scripturi** pentru wizard-ul de instalare (Inno Setup).

---

## Structura folderului (dupa ce rulezi build_all.ps1)

```
build_installers/
  exe/                   – exe-uri si imagini (folosite de scripturile .iss)
    Soft_Ofertare.exe
    Soft_Admin.exe
    Naturen2.png
    logo.ico
    app_settings.json    – optional

  installer_ofertare.iss – script pentru wizard instalare Ofertare
  installer_admin.iss    – script pentru wizard instalare Admin

  build_all.ps1          – genereaza exe-urile si le pune in exe\
  build_installers.bat   – compileaza cele doua instalatoare (iscc)
  specs/                 – fisiere PyInstaller (folosite de build_all.ps1)
  assets/                – optional: pui aici logo.ico / Naturen2.png daca nu sunt in radacina proiectului
```

---

## Pas 1: Generezi exe-urile si pui imaginile in folder

1. In **radacina proiectului** (sau in `build_installers\assets`) pui: **logo.ico**, **Naturen2.png** (si optional **despre.gif** pentru Ofertare).
2. Rulezi (PowerShell, din radacina proiectului):

   ```powershell
   .\build_installers\build_all.ps1
   ```

Dupa rulare, in **build_installers\exe** vei avea: **Soft_Ofertare.exe**, **Soft_Admin.exe**, **Naturen2.png**, **logo.ico** (si eventual **app_settings.json**). Scripturile .iss citesc fisierele din **exe\**.

---

## Pas 2: Generezi instalatoarele wizard

Ai doua variante:

**A) Din Inno Setup (programul pentru wizard)**  
- Deschizi **Inno Setup**.  
- File → Open → alegi **installer_ofertare.iss** (din folderul build_installers).  
- Build → Compile. Rezultat: **NaturenFlow_Ofertare_Setup.exe** in acelasi folder.  
- La fel pentru **installer_admin.iss** → **NaturenFlow_Admin_Setup.exe**.

**B) Din linia de comanda**  
- Deschizi un prompt in folderul **build_installers**.  
- Rulezi:
  ```cmd
  build_installers.bat
  ```
  (sau, daca ai `iscc` in PATH: `iscc installer_ofertare.iss` si `iscc installer_admin.iss`).

Setup-urile apar in folderul **build_installers**.

---

## Rezumat

| Vrei sa...              | Faci... |
|-------------------------|--------|
| Ai in folder cele 2 exe + imagini + scripturi wizard | Rulezi `build_all.ps1` din radacina proiectului. |
| Compilezi wizard-ul Ofertare | Deschizi **installer_ofertare.iss** in Inno Setup → Compile (sau rulezi `iscc installer_ofertare.iss`). |
| Compilezi wizard-ul Admin    | Deschizi **installer_admin.iss** in Inno Setup → Compile (sau rulezi `iscc installer_admin.iss`). |

Tot ce ai nevoie (exe, Naturen2.png, logo.ico, cele doua scripturi .iss) este in **acelasi folder** – build_installers.
