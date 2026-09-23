# Analyse factuelle du notebook historique

## Statut et perimetre

Ce document decrit le comportement constate de `graph_to_ontome.ipynb`.
Il sert de base de discussion pour definir un produit de remplacement. Ce
notebook est un materiel historique : il n'est pas appele par le paquet Python
ni par ses tests (`README.md`, lignes 40-42).

Les references `NB` ci-dessous designent les numeros de lignes physiques du
fichier JSON du notebook, et non des cellules Jupyter. Elles permettent de
retrouver le code source exact.

Le notebook est actuellement preconfigure pour DoReMus 0.2. Il n'est pas un
importeur generique sans modification manuelle de cellules et de fichiers de
reference.

Fichiers examines :

- `graph_to_ontome.ipynb` : notebook principal RDF vers XML.
- `references/list_ns_uri_220914.json` : registre historique URI/version vers
  identifiant de namespace OntoME.
- `references/schemaImportXmlwithReferences.xml` : XSD utilise par le
  notebook.

Hors perimetre : ce document ne juge pas la validite metier des choix de
mapping et ne presume pas que le comportement historique doive etre conserve.

## Objet du notebook

Le notebook lit une ontologie RDF, selectionne ses classes et proprietes,
fabrique un XML d'import OntoME et tente une validation XSD. Il utilise :

- `rdflib` pour parser le graphe RDF et executer les requetes SPARQL ;
- `lxml.etree` pour construire, serialiser et valider le XML ;
- un registre JSON local pour trouver les IDs de namespaces OntoME externes.

Il automatise notamment la decoupe d'URI, l'extraction de labels et la
production d'elements XML. Il ne remplace pas les decisions editoriales : les
metadonnees du namespace, les versions de references et plusieurs conventions
RDF sont saisies ou modifiees manuellement.

Sources : `NB:13-27`, `NB:63-70`, `NB:186-217`.

## Flux d'execution observe

| Etape | Traitement | Entrees principales | Sortie ou effet | References |
| --- | --- | --- | --- | --- |
| 1 | Importe les bibliotheques Python. | Environnement Jupyter. | Modules charges. | `NB:63-70` |
| 2 | Definit l'ontologie a traiter. | Variables editees dans une cellule. | Nom de fichier, URI de perimetre, libelle et version cibles. | `NB:78-109` |
| 3 | Definit les prefixes RDF/SPARQL. | Dictionnaire `ns` code dans le notebook. | Prefixes disponibles aux requetes. | `NB:117-145` |
| 4 | Choisit des versions de namespaces externes. | Dictionnaire `specified_versions`. | Version OntoME demandee pour certaines URI. | `NB:153-178` |
| 5 | Charge le registre OntoME historique. | `references/list_ns_uri_220914.json`. | Dictionnaire `ontome_ns`. | `NB:186-217` |
| 6 | Charge le XSD. | `references/schemaImportXmlwithReferences.xml`. | Validateur `xmlschema`. | `NB:225-252` |
| 7 | Construit le chemin source et parse le RDF. | `input/{current_version}.ttl`. | Graphe RDF `g`. | `NB:261-350` |
| 8 | Liste les types RDF et initialise leur suivi. | Graphe `g`. | Dictionnaire `typed_decls`, sorties de console. | `NB:339-350` |
| 9 | Audite les predicats des classes. | Ressources `owl:Class`. | Compteurs et predicats inconnus affiches. | `NB:375-411` |
| 10 | Audite les predicats des proprietes. | `owl:ObjectProperty`, `owl:DatatypeProperty`. | Compteurs et predicats inconnus affiches. | `NB:440-483` |
| 11 | Lit des metadonnees de l'ontologie. | Triples du sujet `being_imported`. | URI, date, description, prefixe. | `NB:518-548` |
| 12 | Cree la racine XML et ses metadonnees. | Variables manuelles et metadonnees RDF. | Element `<namespace>`. | `NB:582-741` |
| 13 | Declare des fonctions utilitaires. | URI, RDF, registre externe. | Fonctions de decoupe, labels et resolution. | `NB:800-1023` |
| 14 | Exporte les classes. | Classes OWL dans le perimetre. | Elements `<class>` en memoire. | `NB:1046-1232` |
| 15 | Exporte les proprietes. | Proprietes objet et datatype du perimetre. | Elements `<property>` en memoire. | `NB:1303-1620` |
| 16 | Assemble le document. | Classes, proprietes, IDs externes, description. | Arbre XML final. | `NB:1638-1693` |
| 17 | Valide et ecrit le XML. | Arbre XML et XSD. | Fichier XML date dans `output/`. | `NB:1719-1751` |
| 18 | Affiche les declarations non traitees et reparse le XML. | `typed_decls`, fichier ecrit. | Diagnostics de console. | `NB:1761-1786` |

L'ordre d'execution est une condition implicite. Les compteurs d'execution
stockes dans le notebook ne suivent pas toujours l'ordre visuel des cellules.
Les sorties enregistrees ne demontrent donc pas un run propre et reproductible
de bout en bout.

## Entrees, proprietaires et contrats implicites

| Entree | Emplacement ou mode de saisie | Contrat implicite | Utilisation |
| --- | --- | --- | --- |
| Ontologie RDF | `input/{current_version}.ttl` | Fichier parse par RDFLib ; l'extension doit etre modifiee a la main pour un autre format. | Source de toutes les classes, proprietes et relations. |
| `current_version` | Cellule de configuration. | Nom de base du fichier source et de sortie. | Construit les chemins d'entree/sortie. |
| `being_imported` | Cellule de configuration. | URI contenue dans les ressources a importer et sujet exact des metadonnees RDF. | Filtre le perimetre et lit les metadonnees. |
| `import_desc` | Cellule de configuration. | Libelle anglais du namespace cible. | Ecrit `<standardLabel lang="en">`. |
| `import_version` | Cellule de configuration. | Version editoriale du namespace cible. | Ecrit `<version>`. |
| `ns` | Cellule de configuration. | Prefixes RDF utilises par les requetes SPARQL. | Recherche de labels. |
| `specified_versions` | Cellule de configuration. | URI de namespace externe vers version OntoME choisie. | Choisit un ID parmi les versions du registre. |
| Registre OntoME | `references/list_ns_uri_220914.json`. | Objet JSON `URI -> [{version, id}]`. | Transforme une URI externe en ID de namespace OntoME. |
| XSD | `references/schemaImportXmlwithReferences.xml`. | XSD local compatible avec le serveur OntoME vise. | Validation locale du XML. |
| Repertoire de sortie | `output/`. | Existe avant l'execution. | Recoit le XML date. |

Les chemins sont relatifs au repertoire depuis lequel Jupyter est lance. Le
notebook ne les ancre pas au repertoire qui contient le notebook et ne cree pas
`output/`.

### Configuration actuellement codee

La configuration stockee dans le notebook concerne DoReMus :

```python
current_version = "doremus"
being_imported = "http://data.doremus.org/ontology#"
import_desc = "DoReMus v0.2"
import_version = "0.2 (05/06/2017)"
```

Source : `NB:100-109`.

## Fonctions Python principales

| Fonction | Role | Dependances implicites | Regles et comportements notables | References |
| --- | --- | --- | --- | --- |
| `cut_about(about_val)` | Decoupe une URI en namespace source, nom local, identifiant et libelle derive. | `nsuri`, `ontome_ns`, `get_ns_nb`. | Coupe sur `#`, sinon sur `/`; prend ce qui precede le premier `_` comme identifiant. Retourne `current` pour le namespace courant. Un `except` nu affiche l'URI puis retourne implicitement `None`. | `NB:820-854` |
| `get_languages(subject, predicate)` | Recupere les litteraux d'un sujet/predicat. | `g`, `ns`, moteur SPARQL RDFLib. | Retourne une liste de dictionnaires `{'lg', 'txt'}`. Aucune gestion d'erreur. | `NB:884-924` |
| `transform_label(entry)` | Nettoie les prefixes d'identifiant dans un libelle. | Module `re`. | Reconnait notamment `E5_...` et `P14i_...`; cette convention est CRM-like. | `NB:944-967` |
| `get_ns_nb(link)` | Trouve l'ID OntoME d'un namespace externe. | `specified_versions`, `ontome_ns`, `ns_decl_list`. | Essaie URI, URI avec `/`, URI avec `#`; compare des versions a l'identique. Affiche un avertissement si aucune entree ne correspond. | `NB:987-1023` |

Les principaux traitements ne sont pas encapsules dans des fonctions : les
exports de classes et de proprietes sont des blocs de cellules qui dependent
d'un grand nombre de variables globales. Ils ne peuvent pas etre appeles,
testes ou rejoues independamment sans extraire leur code.

## Transformation RDF vers XML effectuee

### Metadonnees de namespace

| Source | Transformation XML | Observation |
| --- | --- | --- |
| `import_desc` manuel | `<standardLabel lang="en">` | Le libelle n'est pas derive de la source RDF. |
| `import_version` manuel | `<version>` | Valeur editoriale manuelle. |
| `dcterms:modified` | `<publishedAt>` | Conversion de date specifique et fragile. |
| `dcterms:contributors` | `<contributors>` | Le predicat singulier `dcterms:contributor` n'est pas lu. |
| `dc:description` | `<description>` | Le code ne renseigne pas `lang`, pourtant requis par le XSD fourni. |
| IDs trouves par `get_ns_nb` | `<referenceNamespace>` racine | Dedoublonnes a la fin du traitement. |

Sources : `NB:520-548`, `NB:606-610`, `NB:632-636`, `NB:663-741`,
`NB:1638-1680`.

### Classes

Seules les ressources URI ayant exactement le type `owl:Class` et dont l'URI
contient `being_imported` sont candidates (`NB:1053-1084`).

| Assertion RDF | Transformation | Limite ou convention |
| --- | --- | --- |
| URI de la classe | `identifierInNamespace` | Identifiant derive par decoupe URI et `_`; aucun `identifierInURI` n'est cree. |
| `rdfs:label` | `standardLabel` localise | Sans label, le notebook fabrique un libelle depuis l'URI. Un label sans langue peut faire echouer la creation XML. |
| `rdfs:subClassOf` URI | `subClassOf` | Ajoute `referenceNamespace` pour une cible externe resolue. |
| `rdfs:comment` ou `skos:scopeNote` | `scopeNote` ou `example` | `rdfs:comment` est prioritaire ; texte commencant par `ex` traite comme exemple. |
| `owl:equivalentClass` | Commentaire XML | La relation n'est pas serialisee semantiquement. |
| `owl:unionOf` | Commentaire XML | La structure OWL n'est pas serialisee. |
| Objet non URI | Commentaire XML | La classe n'est pas importee. |

Sources : `NB:1113-1232`.

### Proprietes

Seules les ressources URI de type exact `owl:ObjectProperty` ou
`owl:DatatypeProperty` et dont l'URI contient `being_imported` sont candidates.
Les proprietes dont le nom respecte une regex d'inverse sont ignorees comme
entites propres (`NB:1310-1338`).

| Assertion RDF | Transformation | Limite ou convention |
| --- | --- | --- |
| `rdfs:label` | `label/standardLabel` localise | Le notebook construit aussi des inverse labels depuis la propriete inverse. Sans label, aucun element `label` n'est cree alors que le XSD l'exige. Un label sans langue produit la valeur fabriquee `lang="None"`. |
| `owl:inverseOf` | Recherche de labels pour `inverseLabel` | La relation `inverseOf` n'est jamais serialisee dans un element XML `inverseOf`. Plusieurs inverses peuvent laisser la variable utilisee ensuite non definie. |
| `rdfs:subPropertyOf` URI | `subPropertyOf` | Reference externe resolue via le registre JSON. |
| `rdfs:domain` URI | `hasDomain` | Plusieurs valeurs, absence ou objet non URI deviennent des textes de remplacement. |
| `rdfs:range` URI | `hasRange` | Plusieurs valeurs, absence ou objet non URI deviennent des textes de remplacement. |
| `xsd:string` | `hasRange` vers `E62`, namespace `1` | Mapping CRM code en dur. |
| `xsd:integer`, `xsd:positiveInteger` | `hasRange` vers `E60`, namespace `1` | Mapping CRM code en dur. |
| `rdfs:comment` ou `skos:scopeNote` | `scopeNote` ou `example` | Heuristique `ex` identique aux classes. |
| Cardinalites RDF/OWL | Aucune sortie | Explicitement non implementees. |

Sources : `NB:1364-1620`.

## Donnees et comportements codes en dur

| Element | Valeur ou regle | Nature | Risque de generalisation |
| --- | --- | --- | --- |
| Ontologie active | DoReMus 0.2. | Configuration produit. | Toute autre ontologie impose une edition manuelle. |
| Prefixes RDF | Table fixe de 14 prefixes, dont CRM, eCRM, FRBRoo et DoReMus. | Convention technique. | Vocabulaire absent a ajouter manuellement. |
| Versions externes | CRM/eCRM `6.2`, DoReMus `0.2`, autres valeurs fixes. | Decision editoriale. | Peut contredire la version effectivement importee. |
| Registre OntoME | Fichier date `220914`. | Donnee de reference locale. | Peut etre obsolete ou incomplet. |
| Identifiant local | Segment avant le premier `_`. | Convention CRM. | Ne convient pas a de nombreuses URI RDF. |
| Libelle de secours | Suppression d'un prefixe regex `^[A-Z]+\d+i?`. | Convention CRM. | Peut modifier un libelle significatif. |
| Perimetre | Test d'inclusion textuel `being_imported in uri`. | Heuristique. | Ne controle pas une frontiere de namespace exacte. |
| Inverse | Regex sur le nom de la propriete. | Convention de nommage. | Ne repose pas uniquement sur `owl:inverseOf`. |
| Exemple | Tout texte commencant par `ex`. | Heuristique editoriale. | Peut classer une explication comme exemple. |
| Datatypes | `xsd:string -> E62`; entiers -> `E60`; namespace `1`. | Decision semantique CRM. | Non justifiee pour un autre contrat OntoME. |
| Date | Traitement de dates anglais et liste finie d'annees bissextiles. | Code utilitaire. | Chemin alphabetique reference une variable `crm` non definie. |

Le registre historique associe notamment CRM `7.1.1` a l'ID OntoME `188`, CRM
`5.0.4` a `187` et CRM `6.2` a `1`. Cette information est une archive de 2022,
pas une preuve de l'etat courant d'OntoME.

Source : `references/list_ns_uri_220914.json`, lignes 6-15.

## Rapports et artefacts produits

| Artefact | Forme | Contenu | Limite |
| --- | --- | --- | --- |
| Inventaire de types | Sortie Jupyter. | Valeurs de `rdf:type` rencontrees. | Non versionne, non structure, non exporte. |
| Audit de predicats | Sortie Jupyter. | Predicats de classes/proprietes non attendus. | N'empeche pas la generation. |
| Suivi de declarations | Dictionnaire `typed_decls` et sortie Jupyter. | Ressources typees non marquees comme traitees. | Ne distingue pas correctement les constructions hors perimetre. |
| Erreurs XSD | Sortie Jupyter. | Exceptions de validation imprimees. | Ne bloque pas l'ecriture du fichier. |
| XML d'import | `output/output_{current_version}_{YYYYMMDD_HHMMSS}.xml`. | Document XML destine a OntoME. | Horodate, sans manifeste, checksum, trace ni rapport machine. |
| Reparse XML | Sortie Jupyter. | Verification de bonne formation apres ecriture. | Ne refait pas la validation XSD. |

Sources : `NB:401-411`, `NB:473-483`, `NB:1719-1786`.

## Limites et defauts observables

Les points suivants sont factuels : ils decrivent le code, sans conclure sur
leur priorite produit.

1. Les exceptions de parsing RDF et de validation XSD sont affichees, puis le
   flux peut continuer (`NB:329-350`, `NB:1719-1723`).
2. Le XSD exige `description/@lang`, mais le notebook ecrit une description
   sans attribut `lang` (`NB:1675-1680`, XSD lignes 18-25).
3. L'export peut ecrire des valeurs comme `None`, `Several` ou un message
   d'erreur dans `hasDomain` et `hasRange` (`NB:1475-1487`, `NB:1534-1548`).
4. Les notes et exemples peuvent etre perdus : `textProperties` est cree selon
   des conditions qui ne couvrent pas tous les cas, et les exemples de
   proprietes mono-lignes ne sont pas tous ajoutes (`NB:1167-1192`,
   `NB:1579-1600`).
5. Les constructions OWL telles que unions, restrictions, cardinalites,
   proprietes d'annotation, individus et plusieurs types speciaux sont au
   mieux signales en console ou en commentaire XML ; elles ne sont pas
   preservees comme semantique d'import (`NB:261-287`, `NB:312-322`,
   `NB:1202-1228`, `NB:1281-1283`).
6. Les ressources anonymes ne sont pas gerees de facon uniforme. Le traitement
   de proprietes non URI reference `propElement`, qui n'est pas defini dans ce
   bloc (`NB:1315-1325`).
7. Le chemin de conversion de certaines dates alphabetiques utilise `crm`, une
   variable absente du notebook (`NB:668-700`).
8. `get_ns_nb` contient des affectations inatteignables apres `return` et peut
   retourner implicitement `None` (`NB:1003-1023`).
9. La comparaison de versions est stricte, alors que certaines valeurs du JSON
   sont stockees avec des balises HTML, par exemple `"<p>1.3</p>"`.
10. Les sorties persistantes ne permettent pas de relier chaque feuille XML a
    ses triplets RDF source, sa regle de transformation et sa decision humaine.
11. Une propriete sans `rdfs:label` produit un XML invalide, car le XSD exige
    au moins un element `label` et le notebook ne fabrique pas de secours pour
    les proprietes (`NB:1386-1425`, XSD lignes 105-113).
12. Les labels RDF sont supposes porter une langue. Une langue absente peut
    interrompre l'export de classe ou produire la valeur fabriquee
    `lang="None"` pour une propriete (`NB:919-921`, `NB:1113-1122`,
    `NB:1386-1425`).

## Questions que cette analyse laisse ouvertes

Le notebook ne permet pas de repondre aux questions suivantes. Elles devront
etre tranchees par les responsables OntoME et les proprietaires de l'ontologie :

- Quelle est la source RDF officielle et sa version precise ?
- Quel namespace OntoME cible est autorise et quel est son cycle de publication ?
- Quel catalogue fait foi pour `URI externe -> ID namespace OntoME -> identifiant de terme` ?
- Quelles constructions OWL doivent etre preservees, exclues ou reformulees ?
- Les mappings CRM de datatypes, les conventions d'identifiants et les
  heuristiques sur les exemples sont-ils des regles metier valides ?
- Quels controles doivent bloquer la generation et lesquels sont seulement des
  avertissements ?
- Quelle preuve de concordance entre source, decisions, XML et import serveur
  est attendue ?

## Conclusion factuelle

Le notebook combine quatre responsabilites dans un etat Jupyter mutable :
configuration de projet, catalogue OntoME, transformation RDF/XML et controle
qualite. Il apporte des automatisations utiles, mais elles reposent sur des
conventions non explicitees et sur des donnees locales historiques. Le produit
de remplacement devra separer ces responsabilites avant de choisir son
interface de saisie ou son mode de generation.
