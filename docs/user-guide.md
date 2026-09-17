# Guide utilisateur

## À quoi sert cet outil ?

Vous avez une ontologie RDF, par exemple un fichier RDF/XML. Vous voulez créer un fichier XML que OntoME peut importer.

L'outil ne transforme pas automatiquement n'importe quelle ontologie en XML OntoME. Il fait un travail contrôlé en trois temps :

1. Il lit l'ontologie et relève tout ce qu'elle contient.
2. Il vérifie que chaque information à importer a une traduction OntoME explicitement décidée.
3. Il génère et valide le XML seulement lorsque ces décisions sont complètes.

L'objectif est d'éviter un import XML qui invente des labels, des langues, des identifiants, des domaines, des ranges ou des références externes.

## Ce que l'outil fait et ne fait pas

L'outil sait :

- lire une source Turtle, RDF/XML ou N-Triples ;
- inventorier classes, propriétés, labels, littéraux, langues, datatypes et blank nodes ;
- signaler les constructions RDF/OWL/SKOS inconnues ou hors périmètre ;
- créer des classes et propriétés OntoME lorsque leur mapping est explicite ;
- produire un XML déterministe, une trace de provenance et des rapports ;
- vérifier le XML contre le XSD OntoME fourni avec l'outil.

L'outil ne sait pas :

- deviner quelle classe RDF doit devenir quelle entité OntoME ;
- inventer un identifiant ou un label à partir d'une URI ;
- choisir à votre place une langue, un domaine ou un range ;
- convertir les restrictions OWL, cardinalités, unions, intersections, chaînes de propriétés, individus ou propriétés d'annotation ;
- guider les décisions par un questionnaire interactif.

Autrement dit : vous fournissez l'ontologie et les décisions d'import ; l'outil contrôle ces décisions et fabrique un XML fiable.

```mermaidjs
flowchart TD
    O([Vous installez l'outil<br/>une seule fois])
    A([Vous choisissez une ontologie RDF<br/>pour un projet d'import])
    P[/"Vous lancez init : l'outil crée<br/>un espace de travail pour ce projet"/]
    B[/"L'outil réalise l'audit"/]
    C[[Inventaire RDF et rapport des blocages]]
    D([L'équipe lit le rapport])
    E([Discussion et décisions d'import])
    F([Profils YAML mis à jour])
    G[/"L'outil tente de générer le XML OntoME"/]
    H{Toutes les décisions<br/>sont-elles complètes ?}
    I[[Rapport de génération :<br/>ce qui bloque]]
    J[[XML OntoME généré]]
    K[/"L'outil valide le XML,<br/>la trace et les rapports"/]
    L{Le résultat est-il valide ?}
    M[[Rapport de validation :<br/>erreurs à corriger]]
    N[[XML OntoME prêt à importer<br/>et rapports à conserver]]

    O --> A
    A --> P
    P --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H -- Non --> I
    I --> D
    H -- Oui --> J
    J --> K
    K --> L
    L -- Non --> M
    M --> D
    L -- Oui --> N

    classDef humain fill:#E8F1FF,stroke:#3B82F6,color:#172554;
    classDef outil fill:#FFF4D6,stroke:#D97706,color:#451A03;
    classDef livrable fill:#E7F8EE,stroke:#16A34A,color:#14532D;
    classDef decision fill:#F3E8FF,stroke:#9333EA,color:#3B0764;

    class O,A,D,E,F humain;
    class P,B,G,K outil;
    class C,I,J,M,N livrable;
    class H,L decision;
```

## Installer l'outil

Cette étape ne concerne pas encore votre ontologie. Elle installe le programme et ses dépendances Python sur votre machine.

```bash
git clone git@github.com:lod4hss-semantics/OntoME_importer.git
cd OntoME_importer
git switch cli_importer
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Sous Windows, l'activation est :

```bash
.venv\Scripts\activate
```

Vérifier ensuite :

```bash
ontome-importer --help
```

Cloner le dépôt récupère le code. La commande `python -m pip install -e ".[test]"` installe les bibliothèques nécessaires et crée la commande `ontome-importer`. Elle ne choisit pas votre fichier RDF et n'envoie pas vos fichiers.

## Créer l'espace de travail

L'installation de l'outil se fait une seule fois. Ensuite, `init` fait partie du début de chaque projet d'import : il crée le dossier de travail de ce projet, copie votre RDF et prépare les fichiers de décision.

Un projet d'import regroupe une source RDF, les décisions prises par l'équipe et les fichiers produits. Lancez donc `init` une fois pour chaque ontologie ou import que vous souhaitez traiter séparément. Ne relancez pas `init` pour un projet existant : l'outil refuse d'écraser son dossier de travail.

Vous pouvez lancer `init` depuis n'importe quel dossier du terminal. Les options `--source` et `--workspace` indiquent explicitement où se trouvent le RDF et le nouveau dossier à créer. Les chemins absolus, comme dans l'exemple suivant, évitent toute ambiguïté.

Exemple avec un RDF/XML :

```bash
ontome-importer init \
  --source ~/Téléchargements/mon-ontologie.rdf \
  --format rdfxml \
  --scope-uri-prefix https://mon-organisation.example/ontology/ \
  --workspace ~/Documents/imports/mon-ontologie
```

`--source` est votre fichier RDF original. Il n'est pas modifié. L'outil en copie les octets dans le nouveau dossier de travail et calcule son checksum.

`--workspace` est le nouveau dossier que l'outil doit créer. Il doit ne pas encore exister. L'outil refuse d'écraser un import existant.

`--scope-uri-prefix` désigne le préfixe URI des ressources que vous souhaitez étudier pour cet import. Si votre ontologie utilise plusieurs préfixes à importer, répétez l'option.

```bash
--scope-uri-prefix https://example.org/ontology/ \
--scope-uri-prefix https://example.org/extension/
```

Si le fichier s'appelle `.ttl`, `.nt`, `.rdf`, `.xml` ou `.owl`, le format est déduit automatiquement. Indiquer `--format` reste recommandé lorsqu'il y a un doute.

La commande affiche ensuite la prochaine commande à lancer.

Après `init`, placez-vous dans le workspace créé. C'est à partir de là que les chemins courts `config/...` et `build/...` utilisés par `audit`, `generate` et `validate` sont corrects :

```text
Installer l'outil une fois
        ↓
Lancer init une fois pour un projet d'import
        ↓
Se placer dans le workspace créé
        ↓
Auditer, décider, générer et valider autant de fois que nécessaire
```

Si vous souhaitez importer une autre ontologie, ou conserver un import indépendant pour une nouvelle version de la source, créez un nouveau workspace avec `init` et un autre chemin `--workspace`.

### Ce que `init` crée

```text
mon-ontologie/
  README.md
  source/
    ontology.<extension-rdf>
  config/
    audit.yaml
    generation.yaml
    profiles/
      capability-audit.yaml
      capability-generation.yaml
      namespace-registry.yaml
      mapping-audit.yaml
      mapping-generation.yaml
  build/
```

Le fichier `README.md` de ce dossier répète les prochaines commandes avec les chemins déjà corrects.

| Élément créé | Rôle |
| --- | --- |
| `source/ontology.<extension-rdf>` | Copie de votre ontologie ; l'extension d'origine est conservée et c'est le RDF utilisé par l'import. |
| `config/audit.yaml` | Fichier de départ pour la première analyse. |
| `config/generation.yaml` | Fichier à compléter plus tard pour générer le XML. |
| `capability-*.yaml` | Paramètres techniques fournis par l'outil pour le XSD OntoME. Vous ne les modifiez normalement pas au début. |
| `namespace-registry.yaml` | Liste des namespaces OntoME externes à compléter seulement si votre RDF y fait référence. |
| `mapping-audit.yaml` | Définit le périmètre du premier audit. |
| `mapping-generation.yaml` | Fichier où l'équipe écrira les décisions d'import après l'audit. |

Le XSD OntoME est livré avec l'outil. Vous n'avez pas à chercher ou copier un fichier XSD.

### Les décisions d'import, après l'audit

Le mapping de génération est le fichier qui décrit votre logique métier. Il répond notamment à ces questions :

- Quelles URI source deviennent des classes OntoME ?
- Quelles URI source deviennent des propriétés objet, datatype ou RDF ?
- Quel prédicat fournit le label ?
- Comment calculer l'identifiant local à partir d'une URI source ?
- Quel commentaire ou scope note devient une note XML ?
- Quelle relation RDF devient `subClassOf`, `inverseOf` ou `hasRange` ?
- Quelle URI externe correspond à quel namespace OntoME et quel identifiant ?

Vous ne devez pas répondre à ces questions avant le premier audit. Le rapport d'audit donne la liste exacte des éléments sur lesquels l'équipe doit se prononcer.

La syntaxe complète est dans [Configuration Guide](configuration.md).

## Les commandes, dans l'ordre

Ouvrir un terminal dans votre dossier de travail, pas nécessairement dans le dépôt :

```bash
cd ~/Documents/imports/mon-ontologie
```

### 1. Auditer

```bash
ontome-importer audit \
  --manifest config/audit.yaml \
  --generation-manifest config/generation.yaml \
  --output-dir build/audit \
  --workbook decisions/mapping.xlsx
```

Cette commande utilise exactement le manifest indiqué après `--manifest`. Elle produit :

- `build/audit/inventory.json` : tout ce qui a été lu dans le RDF ;
- `build/audit/audit.json` : le rapport complet détaillé ;
- `build/audit/audit.md` : le résumé à lire en priorité.
- `decisions/mapping.xlsx` : le classeur à compléter avec l'équipe.

L'audit peut se terminer avec le code `0` tout en signalant des blocages. C'est normal : il a terminé son analyse. Travaillez ensuite dans le classeur, pas dans la liste détaillée du Markdown.

### 2. Compléter le mapping

Le classeur distingue les classes, propriétés, références externes, métadonnées et règles. Après les décisions de l'équipe, contrôlez-le puis compilez les YAML utilisés par la génération :

```bash
ontome-importer assist check \
  --manifest config/generation.yaml \
  --workbook decisions/mapping.xlsx \
  --output build/assistant/check-report.json

ontome-importer assist compile \
  --manifest config/generation.yaml \
  --workbook decisions/mapping.xlsx \
  --mapping-output config/profiles/mapping-generation.yaml \
  --registry-output config/profiles/namespace-registry.yaml \
  --report-output build/assistant/compile-report.json
```

`assist check` met à jour les onglets de validation et les couleurs du même classeur, sans modifier les décisions saisies. `assist compile` refuse les décisions incomplètes et remplace les deux YAML indiqués uniquement après contrôle réussi.

Un catalogue RDF externe est facultatif. Lorsqu'il porte un identifiant canonique unique pour chaque URI, l'assistant peut préremplir les références exactes ; vous indiquez explicitement le prédicat qui porte cet identifiant et le namespace OntoME correspondant :

```bash
ontome-importer assist export \
  --manifest config/generation.yaml \
  --catalog chemin/vers/catalogue.rdf \
  --catalog-format rdfxml \
  --catalog-identifier-predicate https://example.org/vocabulary/identifier \
  --catalog-namespace-id 123 \
  --output decisions/mapping-assistant.xlsx
```

Sans catalogue, le classeur liste les références externes détectées et les décisions restent à compléter dans `EXTERNAL_REFERENCES`.

Pour chaque blocage en portée, décider de l'une des actions suivantes :

- compléter le mapping pour une information qui doit être importée ;
- corriger la source RDF si elle est incomplète ou contradictoire ;
- exclure explicitement une information hors périmètre, avec une justification ;
- déclarer précisément une référence externe si elle doit être conservée.

Une génération ne peut pas continuer si une classe n'a pas de label avec langue, si une propriété n'a pas un domaine et un range uniques, ou si une référence externe n'est pas déclarée.

### 3. Générer

Lorsque le mapping de génération est complet :

```bash
ontome-importer generate \
  --manifest config/generation.yaml \
  --output-dir build/import
```

Cette commande relit la source, refait l'audit, résout le mapping, écrit le XML et le valide contre le XSD OntoME.

En succès, elle écrit :

- `build/import/import.xml` ;
- `build/import/generation-trace.json` ;
- `build/import/generation-audit.json`.

En cas de blocage, elle écrit seulement `generation-audit.json`. Elle n'écrit jamais de XML final incomplet.

### 4. Valider le résultat

```bash
ontome-importer validate \
  --manifest config/generation.yaml \
  --xml build/import/import.xml \
  --trace build/import/generation-trace.json \
  --audit build/import/generation-audit.json \
  --output build/import/validation.json
```

Cette commande vérifie le XML, le XSD, les identifiants, les références, les checksums, la trace et la cohérence avec votre RDF et vos profils.

Le XML et ses rapports sont prêts à transmettre seulement lorsque `build/import/validation.json` contient :

```json
"valid": true
```

## Comprendre les retours

| Code | Signification | Action |
| --- | --- | --- |
| `0` | La commande a réussi. | Passer à l'étape suivante ou archiver le résultat et ses rapports. |
| `2` | Un fichier requis, la source, le profil, le XSD ou la destination ne peut pas être utilisé. | Corriger le chemin ou le fichier signalé dans le terminal. |
| `3` | Une décision de mapping ou une validation bloque le résultat. | Lire `audit.md`, `generation-audit.json` ou `validation.json`. |

## Ce qu'il faut conserver

Pour qu'un import soit rejouable, conserver ensemble :

- la source RDF ;
- les deux manifests ;
- les quatre profils ;
- le XML généré ;
- la trace de génération ;
- les audits ;
- le rapport de validation ;
- l'identité du XSD utilisé.

## Aller plus loin

- [Configuration Guide](configuration.md) : syntaxe YAML complète.
- [RDF Inventory](phase-2-rdf-inventory.md) : formats RDF supportés et inventaire.
- Les documents phase 3, 4 et 5 expliquent les détails techniques du moteur ; ils ne sont pas nécessaires pour suivre les commandes de ce guide.
