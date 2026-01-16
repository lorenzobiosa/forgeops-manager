# 🔐 Security Policy

Questo documento descrive come **segnalare vulnerabilità**, quali versioni sono supportate, come gestiamo la **correzione** e il **rilascio** dei fix, e le **linee guida** di sicurezza per chi contribuisce o utilizza il progetto.

> **Principi chiave**
>
> - Segnalazioni **private** e coordinate (**responsible disclosure**).
> - **Nessun segreto nei log** (PAT/TOKEN **mai** loggati).
> - Dipendenze e workflow mantenuti aggiornati (Dependabot/CodeQL/secret scanning).
> - Uso corretto dei **permessi** GitHub (token e repository).

---

## 🛡️ Segnalazione di una vulnerabilità

Se individui una potenziale vulnerabilità, **non aprire una issue pubblica**.
Segnala **privatamente** attraverso:

- **Email**: `lorenzo@biosa-labs.com`
- **GPG consigliato** per informazioni sensibili:
  - Chiave pubblica: `https://github.com/lorenzobiosa/lorenzobiosa/blob/master/keys/gpg-publickey.asc`

Nella segnalazione includi (per quanto possibile):

1.  **Descrizione dettagliata** della vulnerabilità
2.  **Passi di riproduzione** o **Proof‑of‑Concept**
3.  **Impatto atteso** (se noto)
4.  **Contesto/ambiente** (OS, versione Python, versione del progetto, configurazioni rilevanti)

**SLA risposta iniziale**: entro **3 giorni lavorativi**.

---

## 🔄 Processo di triage e risposta

- **Conferma ricezione**: entro **3 giorni lavorativi**
- **Valutazione iniziale**: entro **7 giorni**
- **Assegnazione severità** (linee guida CVSS / impatto reale)
- **Sviluppo e test del fix**: prioritari per le vulnerabilità ad **alto rischio**
- **Rilascio patch**: **ASAP** per High/Critical; include CHANGELOG e note di sicurezza
- **Disclosure**: comunicazione pubblica **solo dopo** che il fix è disponibile e applicabile
- **Embargo**: se necessario, viene concordato un **periodo di silenzio** fino al rilascio

---

## 🧾 Versioni supportate

- **Main / Ultima release**: **attivamente** mantenuta e patchata
- **Release precedenti (LTS, se applicabile)**: solo **patch di sicurezza**
- **Release non supportate**: **nessun** aggiornamento

Per ambienti **production**, usa sempre l’**ultima versione supportata**.

---

## 🔧 Linee guida per l’uso sicuro del toolkit

Il toolkit interagisce con le API GitHub e **può eseguire operazioni distruttive** (es. eliminazioni di cache, release, packages, analyses, dismiss di alerts).
Assicurati di:

- Usare **token** con **permessi minimi necessari** (principio di least privilege):
  - `repo` (accesso a repo privati/pubblici, dove necessario)
  - `workflow` (gestione workflow runs)
  - `read:packages`, `delete:packages` (Packages)
  - `security-events: write` (Code Scanning)
  - **Actions** write (per cancellazione **Actions Cache**)
- In **GitHub Actions** configurare `permissions:` nel workflow per garantire solo i permessi richiesti.
- Eseguire in **dry‑run** quando disponibile prima di operazioni mass‑delete.
- **Verificare** owner/repo/filtro tool in `security.py` per evitare cancellazioni non intenzionali.

> Il progetto **non** logga contenuti sensibili: il **token** non è mai serializzato nei log.
> I log usano `log_event` (JSON/Plain) con **metadati** sicuri (id, chiavi non sensibili, conteggi).

---

## 🧱 Best practice di sicurezza adottate nel codice

- **Logging strutturato** e **idempotente**, senza segreti; eccezioni con stack trace controllato.
- **Gestione rate‑limit** GitHub: attesa fino al reset (`X‑RateLimit‑Reset`) e **retry singolo**.
- **Robustezza**: controlli tipologici su dati API (skip di elementi non conformi), cast sicuri, validazioni di ID/versioni.
- **Configurazione**: setup del logging **solo** in `main()` o nelle CLI — niente side‑effects all’import.
- **Tipizzazione completa**: rimozione di warning Pylance; firme e cast coerenti.
- **Cancellazioni**: sempre **esplicite** e iterate (es. cancellazione cache/release/package/versioni, analyses con follow‑up conferma).

---

## 🧪 Test, CI/CD e scansioni consigliate

Per mantenere sicurezza e qualità, raccomandiamo:

- **pre‑commit** con:
  - `black` (formattazione, line‑length 100)
  - `isort` (ordinamento import)
  - `flake8` (lint)
  - `mypy` (type‑check)
  - `detect-secrets` (scansione di segreti)
- **CI GitHub Actions**:
  - install, lint, type‑check, test e (opzionale) package
- **CodeQL**: analisi SAST su branch protetti
- **Dependabot**: aggiornamenti automatici di dipendenze
- **Secret scanning**: abilitato a livello repository/organizzazione
- **Branch protection**: PR obbligatorie, CI green, almeno 1 **code owner** reviewer

---

## 🚫 Cosa evitare (per contributor e maintainer)

- Non inserire **token/API keys/password** nel codice, commit, issue o log.
- Non serializzare oggetti di risposta **completi** nei log (usa solo metadati sicuri).
- Non aumentare **scope** dei token oltre il necessario.
- Non committare file locali con credenziali (`.env`, dump, chiavi) — controlla `.gitignore`.

---

## 📝 Linee guida per segnalazioni (contributor)

- Segui **responsible disclosure**:
  1.  Segnala **in privato** (email GPG)
  2.  Attendi conferma e coordinamento
  3.  Non divulgare pubblicamente prima del fix
- Nelle PR:
  - Non introdurre regressioni in sicurezza (es. log di segreti, scope eccessivi)
  - Mantieni coerenza con `src.utils.logging` e con i **controlli** tipologici
  - Aggiorna **README/CONTRIBUTING** se cambi il comportamento pubblico

---

## 🔎 Responsible Disclosure

Adottiamo la **responsible disclosure**:

1.  **Segnalazione privata** (email, preferibilmente cifrata)
2.  **Verifica e triage**
3.  **Sviluppo patch** e test
4.  **Rilascio** patch e **comunicazione** pubblica (post‑fix)
5.  **Crediti** ai ricercatori che hanno seguito le linee guida

---

## 📚 Risorse utili

- GitHub Security Advisories: <https://docs.github.com/en/code-security/security-advisories>
- OWASP Top 10: <https://owasp.org/www-project-top-ten/>
- GitHub Secret Scanning: <https://docs.github.com/en/code-security/secret-scanning>

---

## 📬 Contatti

- **Segnalazioni sicurezza**: `lorenzo@biosa-labs.com` (preferibilmente con **GPG**: chiave pubblica disponibile al link indicato)
- **Questioni non sensibili**: apri una **Issue** (bug/feature), senza divulgare dettagli di sicurezza

---

## 📄 Nota legale

Le operazioni fornite dal toolkit (cancellazioni cache/release/packages/versioni, delete/dismiss Code Scanning, pulizia workflow runs) sono **potenzialmente distruttive**.
L’uso è a **tuo rischio e responsabilità**; valida sempre i **perimetri** (owner/repo/tool) e **testa** con `--dry-run` dove disponibile prima di operare in ambienti **production**.

---
