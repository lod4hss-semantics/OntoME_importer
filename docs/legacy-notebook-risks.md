# Risques et limites des notebooks historiques

## Objet

Cette note transforme les constats de `legacy-notebook-analysis.md` et de
`legacy-hardcoded-rules-register.md` en sujets de decision. Elle couvre :

- `graph_to_ontome.ipynb` : RDF/OWL vers XML OntoME ;
- `references/atterebf_original-importer.ipynb` : XML CIDOC CRM vers XML
  OntoME ;
- le registre de namespaces `references/list_ns_uri_220914.json` ;
- le XSD historique `references/schemaImportXmlwithReferences.xml`.

Elle ne conclut pas que toute fonctionnalite historique doit etre reprise. Son
objectif est de rendre visible ce qui doit etre confirme, explicite ou elimine
avant de construire un importeur de production.

Les references `GR` et `CRM` designent les numeros de lignes physiques JSON de
`graph_to_ontome.ipynb` et de
`references/atterebf_original-importer.ipynb`.

## Echelle de priorite

| Priorite | Definition |
| --- | --- |
| Critique | Peut produire ou faire soumettre un import invalide, semantiquement faux ou difficilement reversible. |
| Elevee | Peut perdre, modifier ou attribuer incorrectement des donnees significatives. |
| Moyenne | Compromet la reproductibilite, la generalisation, la maintenance ou la qualite de revue. |
| Faible | Affecte surtout les diagnostics ou l'ergonomie, sans modifier directement les donnees importees. |

`Condition` decrit le declencheur constate dans le code. Ce n'est pas une
estimation statistique de probabilite.

## Synthese pour la reunion

Les risques majeurs ne viennent pas seulement de defauts de code. Les notebooks
ne distinguent pas clairement :

- le contrat XML officiel OntoME ;
- les decisions editoriales du namespace a publier ;
- le catalogue des namespaces et termes OntoME existants ;
- les conventions propres a CRM ou DoReMus ;
- les assertions RDF qui doivent etre conservees, transformees ou exclues.

Ils ecrivent potentiellement un XML apres une erreur, reposent sur un registre
OntoME local de 2022 et masquent des pertes semantiques dans des commentaires
XML ou des sorties Jupyter. Ils ne sont donc pas une base de publication
fiable sans cadrage fonctionnel et technique supplementaire.

## Registre priorise

| ID | Priorite | Risque et condition | Preuve | Consequence | Mesure cible a valider | Decision attendue |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | Critique | Le notebook RDF et le notebook CRM affichent les erreurs XSD mais poursuivent l'execution et peuvent ecrire le XML. | `GR:777-784`, `GR:1719-1751`, `CRM:735-775`. | Un fichier invalide peut etre confondu avec un livrable pret a soumettre. | Echec bloque, aucun XML final publie; rapport structure et code de sortie. | Quelles erreurs autorisent un brouillon, et lesquelles interdisent toute soumission ? |
| R-02 | Critique | Des erreurs de domaine/range deviennent les chaines `None`, `Several` ou un message d'erreur dans le XML. | `GR:1460-1549`. | Un XSD peut accepter la chaine, mais OntoME peut recevoir un faux identifiant. | Interdire les valeurs de repli dans le XML; blocage et diagnostic RDF. | Les proprietes sans domaine/range URI unique sont-elles exclues ou bloquantes ? |
| R-03 | Critique | Le notebook CRM lit les notes de proprietes avec `c.iterchildren(...)`, variable de classe residuelle, au lieu de la propriete `p`. | `CRM:671-680`. | Dans une execution sequentielle normale, chaque propriete lit la note de la derniere classe traitee; l'etat Jupyter peut aggraver cette contamination. | Ne pas reprendre; test de non-regression sur les notes de proprietes. | La preservation des notes de proprietes est-elle requise ? |
| R-04 | Critique | Les IDs de namespaces externes sont resolus depuis un snapshot JSON de 2022; l'absence de version prend la premiere entree. | `GR:987-1023`; `list_ns_uri_220914.json`. | Mauvais namespace OntoME, version CRM incorrecte ou reference non resolue. | Catalogue officiel/API, versionne, avec echec sur ambiguite. | Quelle source fait autorite pour URI -> namespace OntoME -> terme ? |
| R-05 | Critique | La documentation OntoME transmise pour ce cadrage indique qu'un namespace importe est publie et ne peut plus etre modifie. Les notebooks n'ont ni approbation, ni go/no-go, ni reconciliation serveur. | Documentation OntoME transmise, section "Prerequisites & Access rights"; notebooks entiers. | Une erreur peut devenir une publication difficile ou impossible a corriger. | Workflow d'approbation, dossier de preuve, essai controle et controle post-import. | Confirmer le processus officiel de soumission et de correction. |
| R-06 | Elevee | Des assertions OWL sont ignorees, mises en commentaire XML ou seulement affichees : equivalents, unions, restrictions, annotations, individus, cardinalites, types de proprietes. | `GR:261-287`, `GR:312-322`, `GR:1202-1228`, `GR:1281-1283`. | Perte semantique non visible dans le XML final. | Politique par construction : supportee, transformee, exclue avec justification ou bloquante. | Quelles constructions RDF/OWL doivent etre preservees pour le perimetre vise ? |
| R-07 | Elevee | Notes et exemples sont transformes par heuristiques : `rdfs:comment` remplace `skos:scopeNote`; texte commencant par `ex` devient exemple; un texte isole peut ne pas etre serialise. | `GR:1148-1192`, `GR:1560-1600`. | Documentation perdue ou reclassee. | Mapping explicite predicate -> champ XML; rapport de textes exclus. | Comment traiter commentaires, scope notes, exemples et HTML ? |
| R-08 | Elevee | Les conventions CRM sont interpretees par regex : identifiant avant `_`, nettoyage de labels, suppression des proprietes inversees suffixees `i`. | `GR:820-967`, `GR:1330-1382`. | Identifiants ou proprietes errones pour une ontologie hors convention CRM. | Politique d'identifiant et d'inverse configuree par source; pas de supposition lexicale. | Quelles conventions sont garanties par CRM, LRMoo et les autres sources ? |
| R-09 | Elevee | `xsd:string` est mappe silencieusement sur CRM `E62` et les entiers sur `E60`, avec namespace OntoME `1`. | `GR:1503-1515`. | Conversion semantique implicite, incomplete et potentiellement obsolete. | Table versionnee de correspondances ou references externes explicites. | Ces mappings sont-ils valides pour le CRM cible et approuves par OntoME ? |
| R-10 | Elevee | Les metadonnees RDF requierent quatre predicats exacts; leur absence provoque un `KeyError`. Une description est ecrite sans langue; seuls `dcterms:contributors` pluriel est lu. | `GR:520-548`, `GR:663-741`, `GR:1669-1680`; XSD lignes 18-25. | Echec tardif, metadonnees omises ou XML invalide. | Metadonnees de publication fournies par manifeste ou profil; validation avant generation. | Quelles metadonnees sont requises et quelle est leur source d'autorite ? |
| R-11 | Elevee | Les exemples CRM reposent sur le premier element `<examples>`, un parsing XML interne et des manipulations de chaines. L'absence d'exemple peut interrompre le traitement. | `CRM:396-410`, `CRM:694-707`. | Arret ou contenu altere par un exemple absent ou HTML complexe. | Parser structurel et politique de preservation du texte. | Quel niveau de fidelite est attendu pour les exemples riches ? |
| R-12 | Elevee | Le notebook RDF traite les noeuds anonymes de facon incoherente; le chemin de propriete non URI utilise `propElement`, nom non defini. | `GR:1059-1071`, `GR:1315-1325`. | Erreur a l'execution ou perte de semantique pour les structures OWL anonymes. | Diagnostic structurel et blocage/exclusion explicite. | Les restrictions et classes anonymes sont-elles dans le perimetre ? |
| R-13 | Moyenne | Le resultat depend de l'ordre d'execution Jupyter, de variables globales et d'un arbre XML mutable. | `GR:335-345`, `GR:584-1786`; compteurs d'execution du notebook. | Duplications, etat residuel et resultats non reproductibles. | Pipeline unique, parametres explicites et arbre neuf a chaque run. | Quelle preuve de reproductibilite doit accompagner un import ? |
| R-14 | Moyenne | Le suivi `typed_decls` utilise seulement `yes`/`no`; il ne prouve pas que chaque assertion RDF est preservee ou justifiee. | `GR:339-345`, `GR:1084`, `GR:1338`, `GR:1761-1764`. | Faux sentiment de couverture et revue manuelle difficile. | Inventaire et rapport de couverture assertion -> mapping/exclusion. | Quel niveau de tracabilite est attendu avant soumission ? |
| R-15 | Moyenne | Le notebook CRM extrait des quantificateurs depuis une chaine avec regex et positions fixes; le XSD local limite les valeurs et accepte accidentellement la virgule. | `CRM:493-518`, `CRM:568-666`; XSD lignes 159-185. | Quantifications incorrectes, perdues ou impossibles a representer. | Regle CRM officielle ou donnee source structuree; contrat de valeurs valide. | Les quantifications CRM sont-elles obligatoires a l'import ? |
| R-16 | Moyenne | Les chemins et formats sont fixes : Turtle dans `input/`, fichiers locaux `references/`, sorties horodatees dans `output/` ou `data/`. | `GR:216-297`, `GR:1742-1751`; `CRM:55-76`, `CRM:766-775`. | Execution dependante du repertoire et difficile a automatiser. | Manifest de run, chemins explicites, formats declares et artefacts archives. | Quels formats RDF et quelles sources seront officiellement supportes ? |
| R-17 | Moyenne | Les exceptions larges et diagnostics console remplacent des erreurs structurees. | `GR:329-350`, `GR:679-696`, `GR:853-855`, `GR:1441-1447`, `GR:1518-1526`. | Cause racine et statut de l'import difficilement exploitables par une equipe. | Codes d'erreur stables et rapports JSON/Markdown. | Quels rapports et niveaux de details sont attendus par les relecteurs ? |
| R-18 | Faible | Certains libelles et dates fixes sont incoherents, par exemple `"Mai 2021"` avec `lang="en"`. | `CRM:226-254`. | Qualite editoriale insuffisante et confiance reduite dans les metadonnees. | Metadonnees validees, localisees et sourcees. | Qui approuve les libelles, versions et langues ? |

## Risques a confirmer specifiquement pour LRMoo et CRM 7.1.3

Les faits suivants sont connus dans la source LRMoo analysee dans l'espace de
travail : elle declare LRMoo 1.1.1, novembre 2025, et importe CIDOC CRM 7.1.3.
Ils ne suffisent pas a etablir le contrat OntoME correspondant.

| Sujet | Etat actuel | Risque si non tranche |
| --- | --- | --- |
| Namespace OntoME CRM 7.1.3 | L'ID `188` est connu historiquement pour CRM 7.1.1 dans le registre de 2022. Son statut actuel pour 7.1.3 doit etre confirme dans OntoME. | References CRM attribuees a une version incorrecte. |
| Termes CRM externes | L'outil doit connaitre une correspondance exacte URI -> namespace OntoME -> identifiant de terme. | Domaines, ranges, superclasses et superproprietes non resolus. |
| URI OWL de version/import | LRMoo declare `owl:versionIRI` et `owl:imports`. | Metadonnees de version traitees comme references de termes ou exclues sans justification. |
| Cardinalites et inverses | Les notebooks historiques les traitent partiellement, la CLI actuelle les traite differemment. | Regression fonctionnelle non detectee ou attente non satisfaite. |
| XSD et import serveur | Le XSD local valide une structure, sans preuve que le serveur accepte le meme contrat. | Validation locale trompeuse. |

## Decisions structurelles a obtenir

### Donnees d'autorite

1. Quel XSD est officiel, ou est-il publie et comment est-il versionne ?
2. Quel catalogue officiel fournit les namespaces, versions et identifiants de
   termes OntoME ?
3. Quelle version CRM est la reference autorisee pour LRMoo 1.1.1 ?
4. Quelle source RDF ou XML est canonique et comment est-elle figee ?

### Politique semantique

1. Quelles constructions RDF/OWL sont obligatoires, facultatives ou hors
   perimetre ?
2. Quelles correspondances sont autorisees pour les datatypes RDF/XSD ?
3. Comment conserver les labels inverses, les cardinalites, notes et exemples ?
4. Une exclusion doit-elle etre approuvee et documentee ?

### Publication et assurance qualite

1. Quel acteur valide les metadonnees de namespace, references externes et
   exclusions ?
2. Quelles erreurs doivent interdire l'ecriture du XML et lesquelles peuvent
   produire un brouillon de revue ?
3. Quel controle est attendu apres l'import effectif dans OntoME ?
4. Quels artefacts doivent etre archives avec une publication ?

## Matrice de traitement

| Famille | Reponse cible | Verification necessaire |
| --- | --- | --- |
| Contrat XML | Versionner le schema, valider avant publication. | XSD officiel et test d'acceptation serveur. |
| References OntoME | Utiliser un catalogue officiel et des URI exactes. | Provenance, version et regle d'ambiguite. |
| Semantique RDF/OWL | Declarer chaque construction supportee, transformee, exclue ou bloquante. | Approbation OntoME et proprietaire de l'ontologie. |
| Regles source-specifiques | Les porter dans un profil ou adaptateur versionne. | Tests sur source reelle et revue metier. |
| Validation | Echec bloque pour tout artefact de soumission. | Codes de sortie, rapports et essais de regression. |
| Tracabilite | Conserver inventaire, decisions, XML, trace et validation. | Reproduction deterministe et revue d'echantillon. |
| Gouvernance | Formaliser les responsables et les gates de publication. | Workflow approuve par le projet et OntoME. |

## Conclusion

Le principal risque serait de transposer les heuristiques des notebooks en CLI
sans les rendre configurables, tracees et validees. Le produit cible doit
separer la detection technique, la decision editoriale, la resolution des
references OntoME, la generation et la publication. Chaque passage doit produire
un rapport exploitable et avoir une condition de blocage explicite.
