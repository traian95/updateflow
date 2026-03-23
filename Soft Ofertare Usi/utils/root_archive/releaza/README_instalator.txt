================================================================================
  RELEAZA – tot ce trebuie pentru a rula wizard-ul de instalare (Inno Setup)
================================================================================

CONȚINUT FOLDER
---------------
  admin_app\     – aplicația Admin: exe, baza de date, logo, ico, setări
  run_ofertare\  – aplicația Ofertare: exe, baza de date, logo, ico, setări
  installer_admin.iss    – script Inno Setup pentru Soft Admin
  installer_ofertare.iss – script Inno Setup pentru Soft Ofertare

Fișiere incluse în fiecare aplicație:
  - *.exe              (aplicația)
  - date_ofertare.db   (baza SQLite – produse, oferte, clienți, useri)
  - Naturen2.png       (logo afișat în aplicație)
  - logo.ico           (icon pentru fereastră și scurtături)
  - app_settings.json (parametri calcul uși/tocuri, opțional data_mode)

Cum generezi instalatorii (setup wizard)
----------------------------------------
1. Instalează Inno Setup (https://jrsoftware.org/isinfo.php) dacă nu e deja instalat.
2. Deschide un prompt în acest folder (releaza).
3. Rulează:
     iscc installer_admin.iss
     iscc installer_ofertare.iss
4. După compilare apar în acest folder:
     NaturenFlow_Admin_Setup.exe
     NaturenFlow_Ofertare_Setup.exe

Poți rula iscc din linia de comandă sau din Inno Setup: File -> Open -> alegi .iss.

NOTĂ
----
- Baza date_ofertare.db din releaza este copia curentă la momentul build-ului.
  La instalare, utilizatorul primește această bază; dacă folderul de instalare
  nu e scriibil (ex. Program Files), aplicația folosește automat o copie în
  %APPDATA%\Soft Ofertare Usi.
- Pentru o versiune nouă: refă build-ul exe (PyInstaller), copiază din nou
  exe + date_ofertare.db (și eventual app_settings.json) în admin_app\ și
  run_ofertare\, apoi recompilează instalatorii cu iscc.
