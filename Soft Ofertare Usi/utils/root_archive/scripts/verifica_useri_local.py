"""
Verifică utilizatorii din baza locală (cea folosită de Ofertare).
Rulează din rădăcina proiectului:  python scripts/verifica_useri_local.py [username]

Dacă dai un username, afișează doar acel user (căutare case-insensitive).
Altfel afișează toți userii. Nu afișează parola, doar dacă e aprobat și dacă e blocat.
"""
import os
import sys

# rădăcina proiectului pe PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ofertare.config import get_database_path
from ofertare.db import open_db, TABLE_USERS


def main():
    db_path = get_database_path()
    print("Baza locala (Ofertare):", db_path)
    if not os.path.exists(db_path):
        print("Fisierul nu exista. Ruleaza mai intai Ofertare si apoi Sincronizeaza cu Azure.")
        return 1

    db = open_db(db_path)
    try:
        filter_user = sys.argv[1].strip() if len(sys.argv) > 1 else None

        if filter_user:
            db.cursor.execute(
                f"SELECT id, nume_complet, username, approved, COALESCE(blocked,0) FROM {TABLE_USERS} WHERE LOWER(TRIM(username)) = LOWER(?)",
                (filter_user.strip(),),
            )
            rows = db.cursor.fetchall()
        else:
            db.cursor.execute(
                f"SELECT id, nume_complet, username, approved, COALESCE(blocked,0) FROM {TABLE_USERS} ORDER BY username"
            )
            rows = db.cursor.fetchall()

        if not rows:
            if filter_user:
                print(f"\nNu exista niciun user cu username '{filter_user}' in baza locala.")
            else:
                print("\nNiciun user in baza locala.")
            print("-> Pe Ofertare: apasa 'Sincronizeaza cu Azure' si asteapta mesajul de succes.")
            return 0

        print()
        for r in rows:
            id_u, nume, user, approved, blocked = r
            ok = "APROBAT" if approved else "NEAPROBAT"
            bl = " BLOCAT" if blocked else ""
            print(f"  id={id_u}  username={user!r}  nume={nume!r}  {ok}{bl}")

        for r in rows:
            if len(r) > 2 and r[3] == 0:
                print("\nAtentie: userul este NEAPROBAT -> in Admin aproba contul (approved=1).")
                break
    finally:
        db.conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
