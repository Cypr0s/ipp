# Nástroj pro integrační testování – PHP

> [!NOTE]
> Platí zde všechny obecné instrukce pro řešení v jazyce PHP, které jsou 
> uvedeny v [README.md](../README.md) v nadřazeném adresáři.

Při implementaci nástroje pro integrační testování máte v zásadě volnou ruku. K dispozici máte
předpřipravenou kostru s načítáním parametrů z příkazové řádky, kterou můžete libovolně upravit.

## Struktura projektu

- `composer.json`: definuje závislosti a cestu pro automatické načítání PHP tříd.
- `composer.lock`: automaticky generovaný „lockfile“, do kterého Composer uvádí konkrétní verze knihoven,
  které stáhl (slouží pro reprodukovatelnost).
- `phpcs.xml` a `phpstan.neon`: konfigurační soubory pro nástroje PHP_CodeSniffer a PHPStan.
- `src/tester.php`: vstupní skript pro program.
- `src/tester/TesterApp.php`: připravený kód pro načtení argumentů příkazové řádky, inicializaci logování.
  Tuto kostru můžete rovnou dále rozšiřovat.
- `src/Cli/`: pomocný kód pro načítání argumentů příkazové řádky.
- `src/Model/`: definice datových struktur (modelů), které reprezentují jak samotný načtený test, tak i 
  výstupní report. Všechny modely jsou zde podrobně popsány.

Příklad spuštění:

```bash
php src/tester.php --help
```

## Možnosti úpravy šablony

**Povinně** musíte využít modely definované v třídách ve jmenném prostoru `IPP\Tester\Model`. Zde najdete
třídy, které reprezentují načtený test (`TestCaseDefinition`) i výstupní report (`TestReport`). Modely
neměňte (pokud by to z nějakého důvodu pro vás bylo nezbytné, konzultujte to na fóru). Zejména z modelu 
`TestCaseDefinition` však můžete dědit ve vlastním modelu, který bude obsahovat další atributy. 

Můžete (a nemusíte) využít také model `TestCaseDefinitionFile`, který reprezentuje pouze „objevený soubor
s testem“. `TestCaseDefinition` z něj pak dědí (reprezentuje objevený _a rozparsovaný_ soubor).

Mimo tyto modely je řešení **zcela na vás** – poskytnutou kostru nemusíte vůbec využít. Důležité je pouze 
to, aby parametry příkazové řádky odpovídaly zadání. (Použití dodaných modelů zajišťuje správnost výstupního
formátu.)

## Spouštění v kontejneru a interakce s dalšími nástroji

Není specifikován konkrétní způsob, jakým váš testovací nástroj spustí překladač SOL2XML a váš 
interpret. Cesty k překladači a interpretu tedy v podstatě mohou být i napevno definované ve vašem 
kódu, ačkoliv to není považováno za vhodné řešení. Doporučujeme raději použít proměnné prostředí, 
konfigurační soubor nebo vlastní parametry příkazové řádky.

Povinně podporované parametry příkazové řádky jsou popsány v zadání.

## Návratové kódy

Testovací nástroj podporuje pouze následující chybové návratové kódy:
- 1: Zadaná cesta k adresáři s testy neexistuje nebo není adresářem.
- 2: Neplatné argumenty (např. chybějící povinné argumenty, neznámé argumenty, atd.).
     Poznámka: s tímto kódem automaticky ukončuje program knihovna `argparse`.

V nástroji jinak neexistuje žádný „očekávaný“ chybový stav. V případě neočekávaných chyb při
spouštění jednotlivých testů se záznam o této chybě projeví v reportu (vizte model `UnexecutedReason`),
ale testovací nástroj by měl i tak provést všechny testy a skončit s návratovým kódem 0.