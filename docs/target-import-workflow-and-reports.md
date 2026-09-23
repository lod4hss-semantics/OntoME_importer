# Workflow cible et rapports d'import OntoME

## Statut

Ce document est une proposition de cadrage issue de l'analyse des notebooks
historiques. Il definit le processus metier attendu avant de choisir en detail
l'interface humaine, le format de configuration ou les commandes CLI.

Les points marques `[A confirmer]` doivent etre valides avec les responsables
OntoME, le proprietaire de l'ontologie et l'equipe d'import. Ils ne sont pas
des comportements garantis par l'outil actuel.

## Objectif

L'objectif est de produire un import OntoME qui soit :

- fonde sur une source d'ontologie identifiee et figee ;
- compris et approuve par les responsables editoriaux ;
- complet ou explicitement limite ;
- valide techniquement avant soumission ;
- tracable de la source RDF jusqu'au XML puis au resultat OntoME ;
- rejouable sans dependre de l'etat d'un notebook ou de conventions cachees.

Le workflow ne doit pas supposer que toute ontologie RDF est directement
representable dans le XML OntoME. Il doit rendre visibles les ecarts et exiger
une decision explicite pour chaque element en perimetre.

## Principes directeurs

| Principe | Consequence operationnelle |
| --- | --- |
| Source figee | Chaque run reference un fichier, son format, son URI documentaire eventuelle et son checksum. |
| Pas d'inference cachee | Une correspondance, une exclusion, un datatype ou une reference externe est declaree et justifiee. |
| Echec bloque | Un XML de soumission n'est pas ecrit comme resultat valide si une condition bloquante subsiste. |
| Decision humaine explicite | L'outil detecte et documente; les responsables valident les choix semantiques et editoriaux. |
| Provenance complete | Chaque sortie XML est reliée a une regle, une decision et des assertions RDF. |
| Contrats versionnes | XSD, catalogue OntoME, profils de mapping et source sont identifies par version/checksum. |
| Revue proportionnee | Les decisions peuvent porter sur un groupe coherent d'assertions, sans masquer les ressources affectees. |

## Roles et responsabilites

| Role | Responsabilites proposees | Statut |
| --- | --- | --- |
| Proprietaire de l'ontologie | Designe la source canonique, son perimetre, sa version et la signification des donnees. | `[A confirmer]` |
| Responsable editorial du namespace | Approuve URI cible, libelles, version, descriptions, contributeurs et exclusions semantiques. | `[A confirmer]` |
| Referent OntoME | Confirme le XSD, les namespaces de reference, les identifiants et la procedure d'import. | `[A confirmer]` |
| Administrateur OntoME | Detient les droits de soumission et realise ou supervise la publication. | `[A confirmer]` : la documentation fournie reserve l'import aux administrateurs de projet, sans definir les autres responsabilites. |
| Equipe d'import | Execute le workflow, prepare les decisions, corrige les erreurs techniques et archive les preuves. | `[A confirmer]` |
| Relecteur metier | Verifie les mappings, transformations et exclusions ayant un effet semantique. | `[A confirmer]` |
| Outil d'import | Inventorie, detecte, compile, genere, valide et trace; il ne valide pas seul une decision editoriale. | Proposition. |

Une matrice RACI detaillee sera etablie apres confirmation de ces roles.

## Cycle de vie cible

| Phase | Objectif | Entrees | Action de l'outil | Decision humaine | Sorties | Gate de passage |
| --- | --- | --- | --- | --- | --- | --- |
| 0. Cadrage | Declarer l'intention d'import. | Projet, demande, contacts. | Cree ou verifie la fiche d'import. | Type d'import : nouveau namespace, nouvelle version ou mise a jour. | Fiche d'import. | Cible, responsables et perimetre initial identifies; une mise a jour est arretee tant que son processus n'est pas confirme. |
| 1. Preparation | Figer les donnees et contrats de depart. | Source officielle, XSD, catalogue OntoME. | Copie/identifie les artefacts et calcule les checksums. | Approuve source, version, URI et contrats. | Manifeste de run. | Tous les artefacts requis sont disponibles et identifies. |
| 2. Inventaire | Lire le RDF sans le transformer. | Source figee. | Inventorie ressources, triplets, types, langues, datatypes et noeuds anonymes. | Aucune decision semantique. | Inventaire RDF. | Inventaire techniquement complet. |
| 3. Audit | Exposer la representabilite et les ecarts. | Inventaire, capacites XML, profil initial. | Detecte constructions, references externes, collisions et assertions non couvertes. | Decide les sujets a traiter et leur priorite. | Audit de compatibilite. | Chaque constat est affecte a une categorie de decision. |
| 4. Qualification | Prendre les decisions de mapping. | Audit, source, expertise metier. | Controle la coherence et l'exhaustivite des decisions. | Importer, transformer, referencer, exclure, corriger la source ou bloquer. | Journal de decisions. | Chaque element en perimetre a un statut explicite. |
| 5. Resolution externe | Resoudre les liens vers OntoME existant. | URI externes, catalogue OntoME. | Verifie URI, namespace, version, identifiant et statut. | Approuve les namespaces et termes de reference. | Registre de references externes. | Aucune reference requise n'est ambiguë ou non resolue. |
| 6. Compilation | Produire la configuration executable. | Decisions approuvees. | Compile et valide manifests, profils et registre. | Revise le diff des decisions compilees. | Paquet de configuration versionne. | Configuration complete, non ambigue et validee. |
| 7. Generation | Construire un candidat XML. | Configuration, source et XSD. | Re-audite, resout et genere XML plus trace. | Aucune nouvelle decision implicite. | XML candidat, trace, audit de generation. | Aucun blocage technique ou semantique; une approbation doit avoir resolu le blocage ou produit une exclusion explicite. |
| 8. Validation | Verifier le candidat et sa provenance. | XML, trace, audit, source, XSD. | Valide XSD, references, identifiants, couverture et reconstruction. | Accepte ou rejette le paquet de soumission. | Rapport de validation. | Resultat `valide` et approbations obtenues. |
| 9. Soumission | Importer dans OntoME. | Paquet approuve. | Prepare le dossier; [A confirmer] peut assister la soumission. | Administrateur de projet OntoME autorise `[A confirmer]` soumet. | Identifiant de soumission, retour serveur. | Retour OntoME connu et traite. |
| 10. Reconciliation | Verifier le resultat publie. | XML soumis, retour OntoME, namespace publie. | [A confirmer] compare les donnees accessibles. | Accepte le resultat ou ouvre une anomalie. | Rapport de reconciliation. | Ecart accepte ou resolu. |
| 11. Archivage | Conserver la preuve de publication. | Tous les artefacts du run. | Verifie la presence et les checksums. | Cloture le dossier. | Archive d'import. | Paquet complet et lisible dans le temps. |

## Etats de decision

Une decision ne porte pas necessairement sur une seule ressource : une regle
peut couvrir un groupe homogene. Elle doit toutefois enumerer les ressources et
assertions affectees dans son rapport de couverture.

| Etat | Sens | Conditions minimales |
| --- | --- | --- |
| `a_decider` | L'assertion est en perimetre sans traitement approuve. | Constat d'audit present. |
| `importer` | L'assertion est serialisee sans changement semantique declare. | Cible XML et trace definies. |
| `transformer` | L'assertion est convertie selon une regle explicite. | Regle, justification et tests definis. |
| `referencer` | La valeur est une URI externe resolue vers OntoME. | URI exacte, namespace, terme, version et provenance connus. |
| `exclure` | L'assertion est hors perimetre ou non importee. | Justification, responsable et approbation. |
| `corriger_source` | La source doit etre corrigee avant import. | Anomalie documentee et action assignee. |
| `bloquer` | Le run ne peut progresser sans information ou capacite supplementaire. | Motif, impact et proprietaire de la decision. |

## Gates de controle

| Passage | Conditions bloquantes proposees | Preuve attendue |
| --- | --- | --- |
| Cadrage -> Preparation | Type d'import inconnu; responsables absents; namespace cible inconnu; mise a jour sans processus confirme. | Fiche d'import approuvee. |
| Preparation -> Inventaire | Source non canonique; checksum/XSD/catalogue absents. | Manifeste et empreintes. |
| Audit -> Qualification | Inventaire incomplet ou erreur de lecture. | Inventaire et audit produits. |
| Qualification -> Resolution/Compilation | Assertion en perimetre sans decision; exclusion sans justification. | Journal de decisions complet. |
| Resolution -> Generation | URI externe sans namespace/identifiant OntoME exact; version ambigue. | Registre de references valide. |
| Generation -> Validation | Blocage de mapping; XML incomplet; trace absente. | XML candidat, trace et audit de generation. |
| Validation -> Soumission | XSD invalide; reference invalide; couverture incomplete; reconstruction differente; decision sans approbation requise. | Rapport de validation valide, avec liens vers les decisions approuvees, leurs relecteurs et dates. |
| Soumission -> Cloture | Retour OntoME inconnu ou ecart non traite. | Rapport de reconciliation. |

Les listes exactes de controles par gate sont `[A confirmer]` avec OntoME.

## Catalogue de rapports

### Fiche d'import

| Champ | Contenu minimal |
| --- | --- |
| Identite | Identifiant de dossier, projet, demandeur, responsables. |
| Intention | Nouveau namespace ou nouvelle version `[A confirmer]`; une mise a jour est mise en attente tant que son processus reste hors perimetre. |
| Source | URI documentaire, fichier, format, version, checksum et date de recuperation. |
| Cible | URI, ID OntoME si existant, labels, version, statut de publication attendu. |
| Contrats | XSD, catalogue OntoME et profils avec versions/checksums. |
| Perimetre | Selecteurs URI/prefixes exacts, exclusions initiales et regle de rattachement des noeuds anonymes/structures atteignables. |

### Inventaire RDF

Public : equipe technique et relecteurs metier.

| Information | Exigence |
| --- | --- |
| Source lue | Identite et checksum exacts. |
| Ressources | URI et noeuds anonymes, types RDF, nombre de triplets. |
| Vocabulaires | Namespaces, predicats, datatypes et langues detectes. |
| Statistiques | Classes, proprietes, litteraux, relations et structures anonymes. |
| Provenance | Identifiant stable par triplet et ressource. |

### Audit de compatibilite

Public : equipe d'import, referent OntoME et relecteurs metier.

| Information | Exigence |
| --- | --- |
| Constat | Construction RDF/OWL, severite et statut. |
| Portee | Ressource et triplets concernes. |
| Explication | Exemple RDF lisible et impact sur generation. |
| Traitement attendu | Import, transformation, reference, exclusion, correction ou blocage. |
| Regroupement | Une regle peut couvrir plusieurs constats sans les masquer. |

### Journal de decisions

Public : relecteurs metier et OntoME.

| Information | Exigence |
| --- | --- |
| Identifiant | ID stable de decision et version. |
| Perimetre | URI, selecteur ou liste de constats/triplets. |
| Etat | Un des etats de decision definis ci-dessus. |
| Regle | Mapping source -> XML ou motif d'exclusion. |
| Justification | Motivation humaine obligatoire pour exclusions et transformations. |
| Gouvernance | Auteur, relecteur, date et statut d'approbation `[A confirmer]`. |

### Registre de references externes

Public : referent OntoME et equipe technique.

| Information | Exigence |
| --- | --- |
| URI source | Valeur exacte, sans normalisation implicite. |
| Usage | Classes/proprietes source et predicats qui l'emploient. |
| Cible OntoME | Namespace ID, version, identifiant de terme. |
| Provenance | Catalogue, URL, version, checksum ou verification manuelle. |
| Statut | Actif, deprecie, interdit ou non resolu `[A confirmer]`. |
| Decision | Responsable et validation du choix. |

### Rapport de couverture

Public : tous les relecteurs avant generation.

Le rapport doit rendre compte de chaque assertion RDF en perimetre. Il doit
publier le selecteur applique et la regle qui rattache les noeuds anonymes ou
structures atteignables a ce perimetre :

| Etat de couverture | Information |
| --- | --- |
| Importee | Regle appliquee et element XML cible. |
| Transformee | Regle, transformation et justification. |
| Referencee | URI externe et entree de registre utilisee. |
| Exclue | Motif et approbation. |
| Bloquee | Motif, impact et action attendue. |

Ce rapport remplace un simple compteur de ressources traitees : une ressource
peut etre presente alors que certaines de ses assertions sont perdues.

### Rapport de generation et trace de provenance

Public : equipe technique et audit.

| Artefact | Contenu minimal |
| --- | --- |
| Rapport de generation | Source, configuration, compteurs, avertissements, blocages, fichiers produits et checksums. |
| Trace | Pour chaque valeur XML : chemin XML, valeur, attributs, ressource/triplets RDF, regle de mapping ou configuration responsable. |
| Audit de generation | Re-audit sur la source et les profils reellement utilises, avec resultat strict. |

### Rapport de validation

Public : relecteurs avant soumission.

| Controle | Exigence |
| --- | --- |
| Structure | XML bien forme et conforme au XSD versionne. |
| Source et contrats | Checksums source, XSD, catalogue et profils coherents. |
| Identifiants | Unicite, format et references locales. |
| References externes | Namespace et terme OntoME resolus et declares. |
| Couverture | Aucun element XML sans trace; aucune assertion en perimetre sans statut. |
| Approbations | Chaque decision qui exige une approbation est liee a son perimetre, son relecteur, sa date et son statut. |
| Reproductibilite | Reconstruction du meme XML et de la meme trace depuis les entrees archivees. |
| Verdict | `valide`, `invalide` ou `bloque`, avec constats exploitables. |

### Dossier de soumission, reconciliation et archive

| Artefact | Contenu minimal | Statut |
| --- | --- | --- |
| Dossier de soumission | XML, fiche d'import, decisions approuvees, validation, versions et checksums. | Requis avant soumission proposee. |
| Rapport de reconciliation | ID/retour de soumission, resultat publie, ecarts et anomalies. | `[A confirmer]` selon les capacites OntoME. |
| Archive | Tous les artefacts precedents, plus le catalogue de reference utilise. | Requis pour rejouer et auditer propose. |

## Exigences transversales de provenance

Le modele de donnees du futur outil devra permettre les liens suivants :

```text
source RDF
  -> inventaire (ressource, triplet)
  -> constat d'audit
  -> decision humaine
  -> regle compilee
  -> element ou valeur XML
  -> validation locale
  -> soumission OntoME
  -> resultat/reconciliation
```

Chaque lien doit porter un identifiant stable. Les rapports humains peuvent
aggreger ces informations, mais ne doivent pas les rendre impossibles a
retrouver.

## Hors perimetre provisoire

Les points suivants sont explicitement hors perimetre de cette proposition tant
qu'ils n'ont pas ete confirmes :

- appels directs a une API OntoME ;
- automatisation de la soumission serveur ;
- gestion de mises a jour d'un namespace deja publie ;
- choix definitif entre XLSX, interface web ou edition YAML ;
- support de toute construction RDF/OWL non encore qualifiee ;
- politique de correction/rollback cote OntoME.

## Questions de validation pour la reunion

1. Le cycle de vie propose correspond-il a la procedure OntoME reelle ?
2. Quelles phases et quels gates sont obligatoires avant publication ?
3. Qui approuve les mappings, exclusions et metadonnees ?
4. Quel catalogue et quel XSD font autorite, et comment y acceder ?
5. Quels rapports OntoME souhaite-t-il effectivement recevoir ?
6. Peut-on obtenir un resultat de soumission exploitable pour une reconciliation ?
7. Les nouveaux namespaces, nouvelles versions et mises a jour suivent-ils le
   meme processus ?
8. Quelles constructions CRM/LRMoo doivent etre traitees avant un premier
   import pilote ?
