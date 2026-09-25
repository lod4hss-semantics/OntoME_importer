# Guide utilisateur

## À quoi sert cet outil ?

Vous avez une ontologie RDF, par exemple un fichier RDF/XML. Vous voulez créer un fichier XML que OntoME peut importer.

L'outil ne transforme pas automatiquement n'importe quelle ontologie en XML OntoME. Il fait un travail contrôlé en trois temps :

1. Il lit l'ontologie et relève tout ce qu'elle contient.
2. Il vérifie que chaque information à publier a une règle de transformation explicitement décidée.
3. Il génère et valide le XML seulement lorsque ces décisions sont complètes.

L'objectif est d'éviter un XML d'import qui invente des labels, des langues, des identifiants, des domaines, des ranges ou des références externes.

L'outil ne réalise pas un alignement sémantique entre l'ontologie source et OntoME. Il publie les classes et propriétés de la source dans le nouveau namespace OntoME décrit par le projet d'import. Lorsqu'une ressource source référence un terme d'un namespace déjà présent dans OntoME, le XML produit une référence technique vers ce namespace et cet identifiant de terme. Par exemple, une sous-classe de `.../E89_Propositional_Object` peut devenir une référence à `E89` avec l'attribut `referenceNamespace` correspondant au namespace OntoME de la version CRM concernée.

Le logiciel conserve temporairement quelques noms internes historiques contenant `mapping`. Ils ne correspondent pas à un alignement sémantique : les décisions de publication sont prises dans la revue terminale et l'outil génère ensuite ses profils techniques.

## Ce que l'outil fait et ne fait pas

L'outil sait :

- lire une source Turtle, RDF/XML ou N-Triples ;
- inventorier classes, propriétés, labels, littéraux, langues, datatypes et blank nodes ;
- signaler les constructions RDF/OWL/SKOS inconnues ou hors périmètre ;
- créer des classes et propriétés dans le namespace OntoME cible lorsque leurs règles de transformation sont explicites ;
- produire un XML déterministe, une trace de provenance et des rapports ;
- vérifier le XML contre le XSD OntoME fourni avec l'outil.

La liste précise des assertions RDF/RDFS/OWL/SKOS acceptées et de celles qui bloquent est définie dans la [Semantic Policy](semantic-policy.md). L'outil ne fait aucune inférence OWL ou RDFS.

L'outil ne sait pas :

- décider quelles ressources RDF publier, ni quelles ressources exclure ;
- deviner une règle d'identification ou inventer un label ;
- choisir à votre place une langue, un domaine ou un range ;
- convertir les restrictions OWL, cardinalités, unions, intersections, chaînes de propriétés, individus ou propriétés d'annotation ;
- guider les décisions par un questionnaire interactif.

Autrement dit : vous fournissez l'ontologie, le périmètre de publication et les règles de transformation ; l'outil contrôle ces décisions et fabrique un XML fiable.

```mermaidjs
flowchart TD
    O([Vous installez l'outil<br/>une seule fois])
    A([Vous choisissez une ontologie RDF<br/>pour un projet d'import])
    P[/"Vous lancez init : l'outil crée<br/>un espace de travail pour ce projet"/]
    B[/"L'outil réalise l'audit<br/>et prépare la revue"/]
    C[[Inventaire RDF, résumé<br/>et file de revue]]
    D([L'équipe répond aux questions<br/>dans le terminal])
    E([Discussion et décisions d'import])
    F[/"L'outil contrôle les décisions<br/>et signale les blocages"/]
    Q{La revue est-elle<br/>complète ?}
    R[/"L'outil compile les profils<br/>depuis les décisions"/]
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
    F --> Q
    Q -- Non --> D
    Q -- Oui --> R
    R --> G
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

    class O,A,D,E humain;
    class P,B,F,R,G,K outil;
    class C,I,J,M,N livrable;
    class H,L,Q decision;
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
| `mapping-generation.yaml` | Fichier compilé où l'équipe publie les décisions d'import après l'audit. |

Le XSD OntoME est livré avec l'outil. Vous n'avez pas à chercher ou copier un fichier XSD.

### Les décisions d'import, après l'audit

Le profil de transformation de génération est nommé techniquement `mapping-generation.yaml`. Il décrit les règles de publication décidées pour votre import. Il répond notamment à ces questions :

- Quelles URI source deviennent des classes dans le namespace OntoME cible ?
- Quelles URI source deviennent des propriétés objet, datatype ou RDF dans ce namespace ?
- Quel prédicat fournit le label ?
- Quelle règle explicite fournit l'identifiant local : suffixe d'URI, capture regex ou valeur littérale d'un prédicat ?
- Quel commentaire ou scope note devient une note XML ?
- Quelle relation RDF devient `subClassOf`, `inverseOf` ou `hasRange` ?
- Quelle règle transforme une URI externe en référence technique vers un namespace OntoME existant et un identifiant de terme ?
- Quelle décision approuvée justifie une règle de transformation, une exclusion ou une exception éditoriale ?

Vous ne devez pas répondre à ces questions avant le premier audit. Le rapport d'audit donne la liste exacte des éléments sur lesquels l'équipe doit se prononcer. Il ne demande pas de décider d'un alignement sémantique avec OntoME : les ressources sélectionnées sont publiées dans le namespace cible.

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
  --output-dir build/audit
```

Cette commande utilise exactement le manifest indiqué après `--manifest`. Elle produit :

- `build/audit/inventory.json` : tout ce qui a été lu dans le RDF ;
- `build/audit/audit.json` : le rapport complet détaillé ;
- `build/audit/audit.md` : le résumé à lire en priorité.
- `build/audit/review-queue.json` : la file de revue utilisée par le terminal.

L'audit peut se terminer avec le code `0` tout en signalant des blocages. C'est normal : il a terminé son analyse. Lancez ensuite la revue terminale.

### 2. Revoir les décisions de publication

La revue est locale et guidée. Elle enregistre les décisions dans `decisions/review.json` sans exposer les profils techniques.

```bash
ontome-importer review start \
  --manifest config/generation.yaml \
  --session decisions/review.json

ontome-importer review resources --session decisions/review.json
ontome-importer review status --session decisions/review.json
ontome-importer review check --session decisions/review.json
ontome-importer review finalize \
  --manifest config/generation.yaml \
  --session decisions/review.json
```

Lorsqu'une relation RDF pointe vers un terme déjà publié dans OntoME, sélectionnez d'abord le namespace par son URI et sa version. Le registre OntoME livré avec l'outil vérifie cette sélection et la commande télécharge ensuite un catalogue RDF/XML local et traçable. Par exemple, pour CIDOC CRM 7.1.3 :

```bash
ontome-importer namespaces fetch \
  --uri http://www.cidoc-crm.org/cidoc-crm/ \
  --version 7.1.3 \
  --output references/ontome/crm-7.1.3.rdf
```

Le catalogue exporté par OntoME fournit les identifiants canoniques dans `skos:notation`. La revue télécharge et vérifie ce catalogue après confirmation de la dépendance. Les références sont ensuite résolues automatiquement ; ne saisissez pas d'identifiant OntoME par déduction d'URI. Si une URI externe est absente du catalogue sélectionné, elle reste bloquante et le terminal indique l'URI, le namespace et la version à clarifier.

Pour un identifiant local, choisissez une règle explicite. L'outil peut extraire un suffixe d'URI, appliquer une capture regex ou utiliser la valeur littérale unique d'un prédicat. Par exemple, si l'ontologie source porte les identifiants canoniques `F1` ou `R1` dans `skos:notation`, le profil peut définir :

```yaml
identifier_in_namespace:
  source: literal_predicate
  predicate: http://www.w3.org/2004/02/skos/core#notation
```

Cette règle ne signifie pas que toute `skos:notation` doit devenir un identifiant OntoME. Elle l'autorise uniquement pour les ressources couvertes par cette règle de transformation. La génération exige alors exactement un littéral non vide et en conserve la provenance.

Pour chaque blocage en portée, décider de l'une des actions suivantes :

- compléter une règle de transformation pour une information qui doit être publiée ;
- corriger la source RDF si elle est incomplète ou contradictoire ;
- exclure explicitement une information hors périmètre, avec une justification ;
- déclarer une règle ou une exception externe si la référence doit être conservée.

Enregistrez aussi la décision dans `DECISIONS` avec son périmètre, sa justification, son approbateur, sa date et une référence durable. Une décision liée à une assertion qui serait générée doit être `approved`; sinon elle bloque la génération. `EDITORIAL_EXCEPTIONS` est réservé à un domaine ou range absent dans le RDF et exige les mêmes preuves d'approbation.

Une génération ne peut pas continuer si une classe n'a pas de label avec langue, si une propriété n'a pas un domaine et un range uniques, ou si une référence externe n'est pas déclarée.

### 3. Générer

Lorsque le profil de transformation de génération est complet :

```bash
ontome-importer generate \
  --manifest config/generation.yaml \
  --output-dir build/import
```

Cette commande relit la source, refait l'audit, applique les règles de transformation, écrit le XML et le valide contre le XSD OntoME.

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
| `3` | Une règle de transformation, une décision ou une validation bloque le résultat. | Lire `audit.md`, `generation-audit.json` ou `validation.json`. |

## Ce qu'il faut conserver

Pour qu'un import soit rejouable, conserver ensemble :

- la source RDF ;
- les deux manifests ;
- les cinq profils ;
- `decisions/review.json`, son journal et les catalogues OntoME téléchargés ;
- les profils internes compilés par `review finalize` ;
- le XML généré ;
- la trace de génération ;
- les audits ;
- le rapport de validation ;
- l'identité du XSD utilisé.

## Aller plus loin

- [Configuration Guide](configuration.md) : syntaxe YAML complète.
- [RDF Inventory](phase-2-rdf-inventory.md) : formats RDF supportés et inventaire.
- Les documents phase 3, 4 et 5 expliquent les détails techniques du moteur ; ils ne sont pas nécessaires pour suivre les commandes de ce guide.
