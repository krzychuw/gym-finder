# Wspólne obiekty sportowe

Wyszukiwarka siłowni/basenów w całej Polsce, które przyjmują wejścia z kilku
różnych pakietów sportowych naraz (Medicover Sport, Multisport, BeActive) —
żeby łatwo znaleźć wspólny obiekt, gdy znajomi mają różne karty.

Aplikacja to w 100% statyczna strona (HTML/CSS/JS + dane w JSON) — nie ma
żadnego backendu. Dane są scrapowane i dopasowywane raz (lub gdy chcesz je
odświeżyć) skryptami Pythona, a wynik zapisywany jest do `static/data/*.json`,
które strona czyta bezpośrednio w przeglądarce.

## Odświeżenie danych (scrapowanie + matching)

```bash
./setup.sh          # jednorazowo: venv, zależności, przeglądarka Playwright
./refresh_data.sh    # scrapuje Medicover Sport + Multisport, dopasowuje, eksportuje do static/data/
```

## Podgląd lokalny (przed deployem i do sprawdzenia wersji statycznej — to to samo)

```bash
./serve.sh
```

i otwórz `http://localhost:8080`. To serwuje dokładnie folder `static/`,
czyli dokładnie to, co trafia na hosting po deployu — więc to, co widzisz
lokalnie, jest tym, co zobaczą znajomi po wrzuceniu na Netlify.

## Deploy (Netlify Drop)

Przeciągnij folder `static/` na [app.netlify.com](https://app.netlify.com)
("Deploy manually" / pole drag-and-drop). Żeby zaktualizować dane po
`./refresh_data.sh`, przeciągnij folder `static/` ponownie w zakładce Deploys.

## Dodawanie nowego pakietu (np. FitProfit)

1. Dodaj wpis w `config.PACKAGES`.
2. Napisz `scrapers/scrape_<slug>.py` zapisujący do `raw_facilities` z
   odpowiednim `package_id`.
3. Uruchom nowy scraper + `match.py` + `export_static.py` (albo po prostu
   `./refresh_data.sh`, jeśli dodałeś go do tego skryptu).

Matching i frontend obsługują dowolną liczbę pakietów bez zmian w kodzie.
