# DevSecOps Todo — Secure Delivery Platform

Chaîne de livraison sécurisée pour une application web Flask conteneurisée : du commit jusqu'à l'image publiée dans le registry, avec des contrôles de sécurité automatisés et des *security gates* qui bloquent la livraison.

## 1. Architecture

```
 commit / pull request
          │
          ▼
 ┌─────────────────┐
 │ Test Python     │  flake8 + pytest
 └────────┬────────┘
          ▼  (en parallèle)
 ┌──────────────────────────────────────────────┐
 │ Gitleaks (secrets)   Semgrep (SAST)          │
 │ Trivy fs (dépendances + Dockerfile)          │
 └────────┬─────────────────────────────────────┘
          ▼
     SECURITY GATE 1  ── échec ──► pipeline bloqué
          │ ok
          ▼
 ┌─────────────────┐
 │ Docker Build    │  build + test de démarrage (/health)
 └────────┬────────┘
          ▼
 ┌─────────────────┐
 │ Trivy image     │  SBOM (CycloneDX) en parallèle
 └────────┬────────┘
          ▼
     SECURITY GATE 2  ── échec ──► pipeline bloqué
          │ ok
          ▼
 ┌─────────────────────────────┐
 │ CD : GitHub Container       │  push de l'image (branche main)
 │ Registry (ghcr.io)          │
 └─────────────────────────────┘
```

| Fonction | Outil |
|---|---|
| Dépôt Git, CI/CD | GitHub, GitHub Actions |
| Conteneur | Docker (build multi-stage, utilisateur non-root) |
| Registry | GitHub Container Registry (GHCR) |
| Secrets | Gitleaks |
| SAST | Semgrep |
| Dépendances, Dockerfile, image | Trivy |
| SBOM | Trivy (CycloneDX) |
| Application | Flask + gunicorn |

Kubernetes n'est pas utilisé.

## 2. Politique de sécurité

| Sévérité | Action |
|---|---|
| CRITICAL | pipeline bloqué |
| HIGH | pipeline bloqué |
| MEDIUM | information (non bloquant) |
| LOW | information (non bloquant) |

- **Gitleaks** échoue dès qu'un secret est détecté.
- **Semgrep** utilise `--error` : toute règle déclenchée fait échouer le job.
- **Trivy** utilise `severity: HIGH,CRITICAL` et `exit-code: 1`. Les CVE sans correctif disponible sont ignorées (`ignore-unfixed`) : on bloque sur ce qui est réellement corrigeable.
- Les jobs `Docker Build`, `Container Scan`, `SBOM` et `CD` dépendent (`needs`) des contrôles précédents : **aucune image n'est construite, scannée ni publiée si un contrôle de sécurité échoue**.
- Le job `CD` ne tourne que sur un push vers `main`, jamais sur une pull request.

## 3. Durcissement

**Image Docker** : base `python:3.12-slim`, build multi-stage, utilisateur non-root (UID 10001), pas de cache pip, dépendances épinglées, `HEALTHCHECK`.

**Exécution** (smoke test du pipeline) : système de fichiers en lecture seule avec `/tmp` en tmpfs, toutes les capabilities Linux supprimées, `no-new-privileges`.

**Pipeline** : permissions minimales (`contents: read`), `packages: write` accordé uniquement au job `CD`, actions tierces épinglées sur une version précise (pas de `@master`).

## 4. Utilisation

### En local

```bash
pip install -r requirements.txt flake8
flake8 app.py test_app.py --max-line-length 100
python -m pytest -v

docker build -t devsecops-todo .
docker run --rm -p 5000:5000 devsecops-todo
# http://localhost:5000
```

### Dans GitHub

Chaque push sur `main` et chaque pull request vers `main` lance le workflow `.github/workflows/devsecops.yml` (onglet **Actions**). L'image publiée est disponible dans **Packages** (`ghcr.io/<utilisateur>/devsecops-todo`), taguée `latest` et avec le SHA du commit. Le SBOM est téléchargeable comme artefact du run.

## 5. Démonstration

1. Modifier un détail (par exemple le titre dans `templates/index.html`) et faire un commit sur `main`.
2. Onglet **Actions** : montrer `Test Python`, puis les trois scans en parallèle.
3. Montrer que `Docker Build`, `Container Scan` et `SBOM` ne démarrent qu'après les scans.
4. Montrer le job `CD` et l'image dans **Packages**.

## 6. Challenge final

La branche `challenge` contient une version volontairement vulnérable :

| Problème | Fichier | Détecté par |
|---|---|---|
| Secret exposé (clés AWS **fictives**) | `config.py` | Gitleaks |
| Dépendances vulnérables (`requests 2.19.1`, `urllib3 1.23`) | `requirements.txt` | Trivy (dépendances) |
| Dockerfile mal configuré (exécution en root, image `python:3.8` obsolète, mot de passe en `ENV`) | `Dockerfile` | Trivy (misconfiguration) |
| Vulnérabilités applicatives (injection SQL, injection de commande, `debug=True`) | `app.py` | Semgrep |

Une pull request `challenge` → `main` déclenche le pipeline : les contrôles de sécurité échouent, les rapports sont visibles dans les logs, et les jobs `Docker Build`, `Container Scan`, `SBOM` et `CD` ne s'exécutent pas. Sur `main`, qui contient le code corrigé, le pipeline passe et l'image est publiée.

## 7. Limites et améliorations possibles

- Le déploiement s'arrête à la publication de l'image dans GHCR et à un test de démarrage en CI ; il n'y a pas de serveur de production.
- Les données de l'application sont en mémoire (pas de base de données).
- Pistes : signature des images (cosign), scan de l'hôte en production, mise à jour automatique des dépendances (Dependabot), épinglage des actions par SHA de commit.
