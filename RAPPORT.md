# Rapport – Secure Delivery Platform

**Projet** : chaîne CI/CD sécurisée pour une application Flask conteneurisée (GitHub Actions + GitHub Container Registry)
**Dépôt** : `Baye-ngouda/devsecops-todo-`

---

## 1. Enjeux du projet

Une application moderne dépend de dizaines de bibliothèques, d'une image de base, d'un Dockerfile et d'actions CI tierces. Chacun de ces éléments est un point d'entrée possible pour une attaque (attaque de la chaîne d'approvisionnement, secret divulgué, dépendance vulnérable, code malveillant dans une contribution).

L'objectif est de **déplacer la sécurité au plus tôt** (« shift-left ») : à chaque commit, le pipeline vérifie automatiquement la qualité, cherche les secrets, les failles de code, les dépendances vulnérables et les mauvaises configurations, et **bloque la livraison** si un problème grave est détecté. Seule une image conforme atteint le registry.

L'application elle-même (une todo-list Flask) est volontairement simple : l'enjeu est le **processus de livraison**, pas l'application.

## 2. L'application et les technologies

**Application** : « DevSecOps Todo », une todo-list web (ajouter, cocher, supprimer une tâche) écrite en Python avec Flask. Routes : `/` (interface), `/add`, `/toggle/<id>`, `/delete/<id>`, `/api/todos` (JSON) et `/health` (état et version). Les tâches sont gardées en mémoire (pas de base de données : hors périmètre). 6 tests automatisés (pytest) couvrent la santé, l'ajout, le basculement, la suppression, les entrées vides et l'échappement HTML.

| Domaine | Technologie |
|---|---|
| Langage et framework | Python 3.12, Flask 3.1, Jinja2 |
| Serveur d'application | gunicorn (2 workers) |
| Conteneur | Docker, build multi-stage, image `python:3.12-slim`, utilisateur non-root |
| Qualité | flake8, pytest |
| CI/CD | GitHub Actions |
| Sécurité | Gitleaks, Semgrep, Trivy (fs, image), SBOM CycloneDX |
| Registry et livraison | GitHub Container Registry : `ghcr.io/baye-ngouda/devsecops-todo` (tags `latest` et SHA du commit) |
| Gouvernance | règle de protection de `main`, CODEOWNERS, push protection GitHub |

**Lancer l'application** : `docker run --rm -p 5000:5000 ghcr.io/baye-ngouda/devsecops-todo:latest`, puis ouvrir http://localhost:5000.

**Étapes de sécurité réalisées** : (1) détection de secrets, (2) analyse statique du code, (3) analyse des dépendances et du Dockerfile, (4) construction d'une image durcie et test de démarrage, (5) analyse de l'image, (6) génération du SBOM, (7) publication conditionnelle dans le registry, (8) protection de la branche principale. Le détail est dans la partie 3.

## 3. Schéma du pipeline CI/CD

```mermaid
flowchart LR
    A[Commit / Pull request] --> B[Test Python<br/>flake8 + pytest]
    A --> C[Gitleaks<br/>secrets]
    A --> D[Semgrep<br/>SAST]
    A --> E[Trivy fs<br/>dépendances + IaC + secrets]
    B & C & D & E --> G{{GATE 1<br/>4 jobs verts ?}}
    G -->|oui| F[Docker build<br/>+ smoke test durci]
    G -->|non| X[Livraison bloquée]
    F --> H[Trivy image<br/>scan de l'image]
    F --> I[SBOM CycloneDX]
    H & I --> J{{GATE 2}}
    J -->|branche main| K[Push GHCR<br/>latest + SHA]
```

| Étape | Outil | Rôle |
|---|---|---|
| Qualité | flake8, pytest | style et 6 tests fonctionnels |
| Secrets | Gitleaks | détecte clés et mots de passe dans le code et l'historique |
| SAST | Semgrep (`p/python`, `p/flask`) | failles dans le code source |
| Dépendances et IaC | Trivy `fs` | CVE des paquets, mauvaises configurations du Dockerfile, secrets |
| Image | Trivy `image` | CVE de l'image finale |
| Traçabilité | SBOM CycloneDX, artefacts | inventaire des composants conservé comme preuve |
| Livraison | GHCR | publication uniquement depuis `main` |

**Politique de sécurité (security gate)** : CRITICAL et HIGH bloquent le pipeline (`exit-code 1`) ; MEDIUM est un avertissement ; LOW est informatif. Les jobs de build, de scan d'image et de livraison dépendent des scans (`needs`) : ils ne démarrent pas si un scan échoue. Une règle de protection de `main` exige les checks obligatoires avant fusion.

**Durcissement** : image `slim` multi-stage, utilisateur non-root (UID 10001), `HEALTHCHECK`, dépendances épinglées. Le smoke test lance le conteneur en lecture seule, avec `--cap-drop ALL` et `no-new-privileges`. Les permissions du workflow sont limitées à `contents: read` (le job de livraison reçoit seul `packages: write`).

## 4. Analyse de risques

| # | Risque | Impact | Probabilité | Mesure en place | Risque résiduel |
|---|---|---|---|---|---|
| R1 | Secret (clé, mot de passe) committé | Élevé | Moyenne | Gitleaks + Trivy secret + *push protection* GitHub | Faible |
| R2 | Dépendance vulnérable (CVE) | Élevé | Élevée | Trivy fs et image, versions épinglées et vérifiées | Faible à moyen (CVE sans correctif ignorées) |
| R3 | Faille dans le code (injection SQL/commande, `debug=True`) | Élevé | Moyenne | Semgrep, tests | Moyen (règles génériques) |
| R4 | Dockerfile non sûr (root, image obsolète, secret en `ENV`) | Moyen | Moyenne | Trivy misconfig, durcissement | Faible |
| R5 | **Action CI compromise** (chaîne d'approvisionnement) | Très élevé | Faible à moyenne | Versions vérifiées, jamais `@master`, permissions minimales | Moyen (tags non figés par SHA) |
| R6 | **Contribution malveillante** (PR externe) | Élevé | Moyenne | Workflow `pull_request` (jeton en lecture seule, sans secret), approbation des PR de contributeurs externes, revue obligatoire | Moyen (voir partie 5) |
| R7 | Image non conforme publiée | Élevé | Faible | La publication dépend des deux gates et se limite à `main` | Faible |

Vérification des composants : les versions des actions et des dépendances ont été contrôlées avant usage (remarque du prof). Cela s'est révélé important : l'action `trivy-action` a subi une compromission en mars 2026 (anciennes versions malveillantes) ; la version 0.36.0, sûre, est utilisée.

## 5. Partie bonus Red Team

### 4.1 Branche `challenge` (attaque simulée par nous)

Une pull request `challenge` introduit volontairement cinq défauts :

| Défaut introduit | Fichier | Détecté par | Résultat |
|---|---|---|---|
| Clé AWS fictive | `config.py` | Gitleaks (et *push protection* GitHub) | bloqué |
| `requests 2.19.1`, `urllib3 1.23` | `requirements.txt` | Trivy | bloqué |
| Image `python:3.8`, root, mot de passe en `ENV` | `Dockerfile` | Trivy misconfig | bloqué |
| Injection SQL, injection de commande, `debug=True` | `app.py` | Semgrep | bloqué |

Résultat : Gitleaks, Semgrep et Trivy échouent ; build, scan d'image, SBOM et livraison sont **ignorés** ; rien n'atteint le registry.

### 4.2 Contribution malveillante réelle (PR #1)

Un camarade a ouvert une pull request contenant du code qui exécute une commande système pour envoyer des données de l'environnement vers un serveur externe (scénario d'exfiltration de secrets de CI).

Constats honnêtes :
- Le pipeline a bien échoué, mais **uniquement sur le job de tests/lint** ; Gitleaks, Semgrep et Trivy sont restés verts. Les règles génériques de Semgrep n'ont pas signalé un `os.system(...)` avec une chaîne constante.
- La PR n'a pas été fusionnée : la **revue humaine** a repéré le danger, puis la PR a été fermée.
- Le workflow `pull_request` limite les dégâts : une PR externe n'a accès à aucun secret et reçoit un jeton en lecture seule.

**Leçon** : les scanners automatiques ne suffisent pas ; ils doivent être combinés avec une revue obligatoire et des règles adaptées.

### 4.3 Neutralisation des gates par la configuration (PR #3)

Une troisième pull request, intitulée « [RED TEAM — DO NOT MERGE] Les configurations de scanners permettent de neutraliser les gates », a démontré une faille de conception : les scanners lisent leur configuration **dans le dépôt**, donc dans le code de la PR elle-même. Une PR peut ajouter ou modifier un fichier d'ignore ou de configuration (`.trivyignore`, `.gitleaks.toml`, `.semgrepignore`, `trivy.yaml`) pour faire taire les alertes.

Constat : sur cette PR, Test Python, Gitleaks, Semgrep et SCA-Trivy sont restés **verts** ; seul `Docker Build` a échoué, pour une raison sans rapport avec la sécurité. Les gates n'ont donc pas été le facteur bloquant.

**Corrections mises en place** :
- un job **« Garde - configuration des scanners »** qui échoue si le dépôt contient un fichier d'ignore ou de configuration de scanner ; le build en dépend ;
- un fichier **CODEOWNERS** qui exige la relecture d'un propriétaire pour toute modification, en particulier du workflow (`.github/`) ;
- une **règle de protection de `main`** : pull request obligatoire, checks obligatoires (dont le job Garde), commit direct refusé.

Limite restante : une PR peut aussi supprimer le job Garde dans le workflow ; seule la revue obligatoire des CODEOWNERS couvre ce cas, d'où la combinaison des deux mesures.

## 6. Ce qu'il resterait à améliorer

1. **Règle Semgrep personnalisée** interdisant `os.system` et `subprocess(..., shell=True)` (le cas de la PR #1).
2. **Revue obligatoire par un second relecteur** pour toutes les PR, et pas seulement celles qui touchent aux fichiers sensibles.
3. **Figer les actions par SHA de commit** (et non par tag), avec Dependabot pour les mises à jour.
4. **Signer les images** (cosign) et publier une attestation de provenance (SLSA).
5. **Déploiement réel** : serveur ou orchestrateur (Kubernetes non exigé ici), avec scan continu de l'image en production et mise à jour automatique.
6. **Politique d'exceptions** : suivre explicitement les CVE ignorées (`ignore-unfixed`) et leur date de revue.
7. **Tests de sécurité dynamiques (DAST)**, par exemple OWASP ZAP sur l'application déployée.
8. **Persistance** de l'application (base de données) et authentification : hors périmètre du TP.

## 7. Conclusion

La chaîne livre automatiquement une image Flask durcie, scannée à quatre niveaux (secrets, code, dépendances/IaC, image), tracée par un SBOM, et **bloque** les contributions dangereuses. Le test Red Team montre aussi les limites : la sécurité repose sur la combinaison de **contrôles automatiques et de revue humaine**.
