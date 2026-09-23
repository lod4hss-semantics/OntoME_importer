# Registre des donnees et regles codees en dur

## Objet et perimetre

Ce registre complete `legacy-notebook-analysis.md`. Il recense les donnees et
regles qui ne sont pas des entrees explicites d'un import dans les deux
notebooks historiques :

- `graph_to_ontome.ipynb`, qui transforme un graphe RDF en XML OntoME ;
- `references/atterebf_original-importer.ipynb`, qui transforme un XML CIDOC
  CRM en XML OntoME.

Il inclut leurs deux fichiers de reference :

- `references/list_ns_uri_220914.json` ;
- `references/schemaImportXmlwithReferences.xml`.

Ce document est factuel. Les propositions dans la colonne `Traitement cible`
ne sont pas des exigences validees : elles identifient les decisions a prendre
avec l'equipe OntoME et les proprietaires des ontologies.

Les references `GR` et `CRM` designent respectivement les numeros de lignes
physiques JSON de `graph_to_ontome.ipynb` et
`atterebf_original-importer.ipynb`.

## Legende de classification

| Categorie | Definition |
| --- | --- |
| Contrat XML local | Regle imposee par le XSD historique fourni dans le depot. Son statut officiel actuel reste a confirmer. |
| Regle OntoME non verifiee | Comportement qui semble concerner OntoME, sans source d'autorite actuelle dans le depot. |
| Convention d'ontologie | Convention propre a CIDOC CRM, DoReMus ou a leur serialisation source. |
| Heuristique d'implementation | Simplification technique decidee dans le code. |
| Defaut apparent | Comportement incoherent, fragile ou techniquement errone. Il ne doit pas etre reproduit par defaut. |

## 1. Contrat XML encode localement

| Regle exacte | Source | Categorie | Risque | Traitement cible |
| --- | --- | --- | --- | --- |
| Racine `<namespace>` et ordre strict : `standardLabel+`, `version?`, `publishedAt?`, `contributors?`, `referenceNamespace*`, `description*`, `classes*`, `properties*`. | XSD lignes 2-27 et 98-209. | Contrat XML local. | L'ordre est significatif pour le XSD. | Obtenir et versionner le XSD officiel avant implementation. |
| Le namespace exige au moins un `standardLabel` avec `lang`; `description` exige aussi `lang`. | XSD lignes 5-25. | Contrat XML local. | Le notebook graphe ecrit une description sans langue. | Confirmer le contrat et imposer une validation bloquante. |
| Chaque conteneur `classes` ou `properties`, lorsqu'il existe, doit contenir au moins un enfant. | XSD lignes 27-97 et 98-208. | Contrat XML local. | Un conteneur vide invalide le document. | Garder si confirme par le XSD officiel. |
| Une classe a des labels localises et peut avoir `subClassOf`, `equivalentClass`, `disjointWith`, `scopeNote`, `example`. | XSD lignes 30-94. | Contrat XML local. | Le notebook graphe ne serialise pas plusieurs relations pourtant admises par ce XSD. | Faire confirmer les relations a conserver. |
| Une propriete exige au moins un `label`, un seul `hasDomain` et un seul `hasRange`; elle peut avoir des relations, quatre quantificateurs et des textes. | XSD lignes 101-205. | Contrat XML local. | Un XML syntaxiquement valide peut contenir un identifiant semantiquement invalide. | Completer par des controles metier explicites. |
| Les quantificateurs acceptent les caracteres `[0,1,2,3,4,5,n]` ou `[1,2,3,4,5,n]`. | XSD lignes 159-185. | Defaut apparent du XSD local. | La virgule est acceptee par la classe de caracteres; les valeurs superieures a 5 sont impossibles. | Valider avec OntoME et CRM avant de reprendre ce contrat. |
| `identifierInNamespace` est optionnel dans le XSD pour classes et proprietes. | XSD lignes 33-39 et 104. | Regle OntoME non verifiee. | Une entite sans identifiant peut valider syntaxiquement mais etre inutilisable. | Confirmer le minimum metier serveur. |

## 2. Configuration fixe du notebook RDF

| Valeur ou regle exacte | Role | Categorie | Risque | Traitement cible |
| --- | --- | --- | --- | --- |
| `current_version = "doremus"` | Compose `input/doremus.ttl` et le nom du XML produit. | Convention DoReMus. | Le notebook n'est pas generique. | Parametre de source explicite. |
| `being_imported = "http://data.doremus.org/ontology#"` | Filtre les URI a exporter et sert de sujet RDF pour les metadonnees. | Convention DoReMus. | Le filtre est une recherche de sous-chaine, pas une frontiere de namespace. | Selecteur URI explicite et compare canoniquement. |
| `import_desc = "DoReMus v0.2"` | Produit le libelle anglais du namespace cible. | Convention DoReMus. | Metadonnee editoriale non derivee ni approuvee dans le flux. | Champ de manifeste avec responsable et preuve. |
| `import_version = "0.2 (05/06/2017)"` | Produit `<version>`. | Convention DoReMus. | Format libre; pas de source d'autorite. | Champ de manifeste. |
| `input/{current_version}.ttl` | Localisation source RDF. | Heuristique d'implementation. | Depend du repertoire de lancement et de Turtle. | Argument/manifest avec format explicite. |
| `references/schemaImportXmlwithReferences.xml` | XSD local. | Heuristique d'implementation. | Aucun checksum ni provenance de telechargement. | Actif versionne et verifie. |
| `output/output_{current_version}_{YYYYMMDD_HHMMSS}.xml` | XML de sortie. | Heuristique d'implementation. | Sortie non deterministe, sans rapport associe. | Repertoire de run et noms stables. |
| Dictionnaire `ns` de 14 prefixes : XML, XSD, RDF, RDFS, OWL, SKOS, VANN, DC, DCT, DoReMus, CRM, eCRM, FRBRoo, eFRBRoo. | Prefixes des requetes SPARQL. | Convention CRM/DoReMus. | Les vocabulaires non listes imposent une modification de code. | Lire les prefixes du graphe ou utiliser des URI completes. |
| Le sujet RDF exactement egal a `being_imported` doit avoir `vann:preferredNamespaceUri`, `dcterms:modified`, `dc:description` et `vann:preferredNamespacePrefix`; seul le premier objet de chaque predicat est lu. | Metadonnees de namespace. | Heuristique d'implementation. | L'absence d'une cle provoque un `KeyError`; les valeurs multiples et predicats alternatifs sont ignores. | Contrat de metadonnees explicite ou champs de manifeste. |
| `dcterms:modified` devient `publishedAt`, avec ajout de `T23:59:59` sur la branche standard. | Date de publication. | Heuristique d'implementation. | La date source est transformee sans regle metier documentee. | Date ISO 8601 validee et conservee sans invention. |
| Seul le predicat non standard `dcterms:contributors` au pluriel est lu; `dcterms:contributor` et `dcterms:creator` ne le sont pas. | Contributeurs. | Defaut apparent. | Des metadonnees source peuvent etre silencieusement omises. | Mapping de predicats approuve. |

Sources : `GR:106-109`, `GR:130-145`, `GR:216-217`, `GR:249-297`,
`GR:1742-1751`.

## 3. Registre de namespaces OntoME historique

### Structure et selection

| Regle exacte | Role | Categorie | Risque | Traitement cible |
| --- | --- | --- | --- | --- |
| `list_ns_uri_220914.json` contient `URI -> [{version, id}]`. | Resout les namespaces de reference. | Regle OntoME non verifiee. | Snapshot local date de 2022, sans mecanisme de mise a jour. | Catalogue officiel, versionne et tracable. |
| `specified_versions` choisit a la main une version par URI externe. | Selectionne un ID parmi les valeurs du JSON. | Regle OntoME non verifiee. | La version demandee peut differer de la source importee et du catalogue. | Choix explicite valide par l'editeur OntoME. |
| `get_ns_nb` essaie successivement `URI`, `URI + "/"`, `URI + "#"`. | Tente de normaliser les URI externes. | Heuristique d'implementation. | Ces URI ne sont pas necessairement equivalentes. | URI exactes; echec sur ambiguite. |
| Avec une URI sans version choisie, le premier enregistrement JSON est pris. | Selection par defaut. | Defaut apparent. | Plusieurs IDs peuvent exister pour une URI. | Aucune selection implicite. |
| En cas d'echec, le code imprime un message et retourne implicitement `None`. | Gestion d'erreur de reference externe. | Defaut apparent. | XML invalide ou erreur tardive. | Erreur structuree bloquante. |

Sources : `GR:168-178`, `GR:987-1023`,
`references/list_ns_uri_220914.json` lignes 1-396. Le snapshot contient 94
URI de namespaces et 100 enregistrements version/ID.

### Valeurs selectionnees manuellement

| URI | Version demandee dans `specified_versions` | Observation |
| --- | --- | --- |
| `http://www.cidoc-crm.org/cidoc-crm/` | `6.2` | Le JSON associe aussi CRM 7.1.1 a 188 et CRM 5.0.4 a 187. |
| `http://erlangen-crm.org/current/` | `6.2` | Alias historique vers les memes IDs CRM. |
| `https://ontome.net/ns/symogih` | `1.3` | Le JSON stocke `"<p>1.3</p>"`; l'egalite stricte echoue. |
| `http://www.cidoc-crm.org/cidoc-crm/CRMarchaeo/` | `1.4.1` | Selection historique manuelle. |
| `https://ontome.net/ns/hisarc-rdf` | `0.0.1` | Le JSON stocke `"<p>0.0.1</p>"`; l'egalite stricte echoue. |
| `https://ontome.net/ns/test-namespace` | `Version 6` | Valeur de test, non generique. |
| `http://momaf-data.utu.fi/` | `0.1` | Le JSON stocke `"<p>0.1</p>"`; l'egalite stricte echoue. |
| `https://ontome.net/ns/gemenet` | `0.1` | Selection historique manuelle. |
| `http://data.doremus.org/ontology#` | `0.2` | Configuration propre a DoReMus. |

Deux URI du registre ont plusieurs IDs sans version permettant de les
discriminer : `https://ontome.net/ns/sdhss` (`3`, `17`) et
`https://ontome.net/ns/cpm` (`22`, `52`). Cela rend la regle "prendre la
premiere entree" non fiable.

## 4. Conventions RDF et transformations du notebook RDF

| Regle exacte | Donnees affectees | Categorie | Risque | Traitement cible |
| --- | --- | --- | --- | --- |
| Seuls `owl:Class`, `owl:ObjectProperty` et `owl:DatatypeProperty` sont exportes. | Declarations RDF. | Heuristique d'implementation. | Les annotations, individus, restrictions, listes et types OWL speciaux sont ignores ou seulement affiches. | Politique de capacite explicite. |
| Les sujets doivent etre des `URIRef`. | Classes et proprietes anonymes. | Heuristique / defaut apparent. | Les classes deviennent des commentaires XML; les proprietes rencontrent un nom non defini. | Diagnostiquer et bloquer ou appliquer une transformation validee. |
| Le perimetre est `being_imported in URI`. | Toutes les ressources candidates. | Heuristique d'implementation. | Faux positifs et faux negatifs de namespace. | URI/prefixe exact parametre. |
| Une URI est coupee sur `#`, sinon sur le dernier `/`; le texte avant le premier `_` devient l'identifiant. | Identifiants, noms et cibles de relations. | Convention CRM/DoReMus. | Depend du nommage CIDOC; non applicable aux URI arbitraires. | Politique d'identifiant configurable. |
| Le libelle de secours retire un prefixe matching `^[A-Z]+\d+i?`. | Labels absents. | Convention CRM. | Modifie des noms non CRM; une propriete sans label ne recoit aucun secours. | Interdire les labels absents ou definir une regle approuvee. |
| Les labels RDF doivent avoir une langue. | Labels de classes et proprietes. | Contrat XML local. | Une langue absente peut interrompre l'export de classe ou fabriquer la valeur `lang="None"` pour une propriete. | Validation pre-generation. |
| Les proprietes inverses sont reconnues aussi par regex `^\w+\d+i\_.*$` et ne sont pas exportees comme proprietes autonomes. | Proprietes inversees. | Convention CRM. | La semantique depend du lexique, pas seulement de `owl:inverseOf`. | Reprendre uniquement une relation RDF explicite. |
| `owl:inverseOf` fournit seulement des `inverseLabel`; la relation XML `inverseOf` n'est pas ecrite. | Proprietes inversees. | Heuristique d'implementation. | Perte de relation; plusieurs inverses laissent une variable non definie. | Confirmer le besoin et mapper la relation explicitement. |
| `rdfs:comment` est prioritaire sur `skos:scopeNote`; un texte commencant par `ex` devient un exemple. | Notes et exemples. | Heuristique d'implementation. | Perte de note et mauvaise classification de texte. | Mapping explicite par predicat. |
| `textProperties` n'est ajoute que si une scope note et un exemple existent tous deux. Pour les proprietes, les exemples mono-lignes sont perdus; les exemples multi-lignes sont decoupes et leur premiere ligne est perdue. | Notes et exemples. | Defaut apparent. | Une ressource qui ne porte que des notes ou que des exemples perd toute sa documentation; les exemples conserves peuvent etre tronques. | Serialiser chaque champ independamment selon une regle explicite. |
| `owl:equivalentClass`, `owl:unionOf` et `rdfs:isDefinedBy` deviennent des commentaires XML ou des diagnostics. | Relations OWL et provenance. | Heuristique d'implementation. | Un commentaire n'est pas une preservation semantique. | Politique de support/exclusion explicite. |
| `rdfs:domain` et `rdfs:range` doivent avoir une seule URI. Sinon, le XML recoit `None`, `Several` ou un texte d'erreur. | Domaines et ranges de proprietes. | Defaut apparent. | Le XSD accepte une chaine mais OntoME peut recevoir un faux identifiant. | Echec bloque et rapport structure. |
| `xsd:string -> E62` et `xsd:integer`/`xsd:positiveInteger -> E60`, avec `referenceNamespace="1"`. | Ranges datatype. | Convention CRM non justifiee. | Mapping semantique silencieux et incomplet. | Catalogue officiel de datatypes et references. |
| Une date non numerique est convertie par tables de mois anglais, liste de bissextiles 2016-2064 et variable `crm` absente. | `publishedAt`. | Defaut apparent. | Erreur a l'execution ou date incorrecte. | Parser standard ISO 8601; echec bloque. |

Sources : `GR:520-548`, `GR:820-967`, `GR:1046-1620`.

## 5. Regles propres au notebook CRM XML historique

| Regle exacte | Donnees affectees | Categorie | Risque | Traitement cible |
| --- | --- | --- | --- | --- |
| Source fixe `data/cidoc_crm_v7.1.1.xml`; sortie datee dans `data/`. | Fichiers source et sortie. | Convention CRM / heuristique. | Non portable et limite a CRM 7.1.1. | Parametres explicites et source figee. |
| Libelle racine `"7.1.1 (Mai 2021)"` porte `lang="en"`; version `"7.1.1 (May 2021)"`. | Metadonnees CRM. | Defaut apparent. | Langue declaree incoherente avec le texte. | Metadonnees editoriales autorisees. |
| Classes et proprietes sont lues dans `./classes/class` et `./properties/property`; IDs depuis `id`; labels depuis premiers `className`, `directName`, `inverseName`. | Structure source CRM. | Convention CRM. | Le parseur ne fonctionne pas pour RDF/OWL ni pour une autre serialisation CRM. | Adaptateur de source versionne. |
| `subClassOf/@id`, `subPropertyOf/@id`, premier `domain/@id` et premier `range/@id` sont utilises directement. | Hierarchie et contraintes. | Convention CRM. | Absence ou pluralite entraine perte ou erreur; aucune reference externe. | Contrat de source explicite. |
| Tous les labels, scope notes et exemples CRM recoivent `lang="en"`; chaque classe et propriete recoit un `textProperties/scopeNote` meme lorsque la source ne fournit aucune note. | Libelles et documentation CRM. | Heuristique d'implementation. | Langue fabriquee, champs vides et contenu source potentiellement deforme. | Preserver la langue source; ne pas creer de champ sans contenu. |
| Chaque `i` minuscule de `subPropertyOf/@id` est retire par `.replace('i', '')`. | Hierarchie de proprietes. | Defaut apparent. | Modifie des identifiants qui contiennent `i` ailleurs qu'en suffixe inverse. | Ne pas reproduire. |
| Les exemples sont pris dans le premier `<examples>`, parses comme XML, puis les balises `li` sont retirees par manipulation de chaines. | Exemples CRM. | Defaut apparent. | L'absence d'exemple de classe interrompt le traitement; pour les proprietes, le gestionnaire d'exception peut relire une variable non definie ou residuelle. | Parser structurel et politique de texte. |
| Les cardinalites sont extraites par regex et positions fixes dans une chaine entre parentheses. | Quantification CRM. | Convention CRM / defaut apparent. | Depend du format textuel, accepte des valeurs invalides et ne supporte pas de valeurs multi-chiffres. | Regle CRM officielle ou donnees structurees. |
| La note de propriete itere sur `c.iterchildren(...)`, variable de classe residuelle, au lieu de `p`. | Notes de proprietes. | Defaut apparent. | Dans un run sequentiel, toutes les proprietes lisent la note de la derniere classe traitee; l'historique Jupyter peut ajouter un autre etat residuel. | Ne pas reproduire; test de non-regression obligatoire. |
| L'absence d'inverse produit `<inverseLabel/>` vide. | Labels de proprietes. | Heuristique d'implementation. | Distingue arbitrairement absence et vide. | Omettre ou renseigner selon le contrat valide. |
| Exceptions de validation imprimees puis sortie ecrite. | Controle qualite. | Defaut apparent. | Un XML invalide semble etre un resultat exploitable. | Echec bloque et rapport. |

Sources : `CRM:55-76`, `CRM:148-152`, `CRM:203-281`, `CRM:368-412`,
`CRM:493-518`, `CRM:551-712`, `CRM:735-813`.

## 6. Etat global et valeurs de repli

| Element | Comportement | Categorie | Traitement cible |
| --- | --- | --- | --- |
| Variables globales Jupyter | `g`, `ns`, `nsuri`, `ontome_ns`, `specified_versions`, `ns_decl_list`, `classes`, `props`, `typed_decls`, `namespace`, `filename` sont lus ou modifies par plusieurs cellules. | Heuristique d'implementation. | Pipeline unique avec parametres explicites et arbre XML neuf par run. |
| `ns_decl_list` | Est modifie par `get_ns_nb`; la declaration racine depend des lookups effectues auparavant. | Heuristique d'implementation. | Collecte pure des references durant la resolution. |
| `typed_decls` avec `"no"`/`"yes"` | Sert de rapport d'elements non traites. | Heuristique d'implementation. | Etats explicites : importe, exclu, bloque, hors perimetre. |
| `"current"` | Sentinelle pour le namespace local. | Heuristique d'implementation. | Reference locale explicite, non serialisee. |
| `"None"`, `"Several"`, messages d'erreur RDF | Ecrits comme domaines/ranges. | Defaut apparent. | Diagnostics hors XML et generation bloquee. |
| `except:` nus | Capturent des erreurs sans contexte dans plusieurs branches. | Defaut apparent. | Exceptions typees, code de sortie et rapport. |
| Arbre XML mutable | Rejouer une cellule peut ajouter des classes, references ou descriptions en double. | Defaut apparent. | Reconstruction deterministe complete a chaque execution. |

Sources : `GR:335-345`, `GR:584-1786`, `CRM:735-813`.

## 7. Matrice de migration

| Comportement historique | Statut propose | Condition avant implementation |
| --- | --- | --- |
| Ordre XML et contraintes syntaxiques | Conserver comme contrat versionne. | XSD officiel obtenu, checksum et date de validite enregistres. |
| Metadonnees de namespace | Rendre configurables. | Responsables editoriaux et champs obligatoires definis. |
| URI externe -> namespace ID OntoME | Remplacer par un catalogue officiel/API. | Source, version, predicate d'identifiant et politique d'ambiguite confirmes. |
| URI locale -> identifiant | Rendre configurable. | Politique d'identifiant par famille d'ontologie. |
| Labels de secours, regex d'inverses, test `ex` | Ne pas reprendre implicitement. | Eventuelle regle metier formalisee et testee. |
| Mappings XSD vers CRM E60/E62 | Remplacer par une table de correspondance versionnee. | Validation OntoME et CRM SIG. |
| Relations OWL non serialisees | Declarer supportees, exclues ou bloquees. | Politique semantique approuvee. |
| Cardinalites CRM | Rendre explicites dans le contrat si requises. | Representation source et valeurs autorisees confirmees. |
| Commentaires XML comme preservation | Supprimer comme mecanisme de mapping. | Rapports de perte/exclusion structures disponibles. |
| Exceptions imprimees, XML tout de meme ecrit | Remplacer. | Politique fail-closed et codes de sortie definis. |
| Rapport `typed_decls` | Remplacer. | Modele de couverture RDF et rapport de decisions definis. |

## 8. Decisions a obtenir

1. Quel XSD et quelle procedure serveur OntoME font autorite pour un nouvel import ?
2. Quel catalogue officiel fournit les IDs de namespaces et les identifiants de termes OntoME ?
3. Quelles conventions CRM doivent etre preservees : identifiants, inverses,
   datatypes, quantifications, notes et exemples ?
4. Quelles assertions RDF/OWL sont acceptables, bloquees ou explicitement
   exclues du perimetre de l'import ?
5. Quelles informations de namespace sont fournies par la source et lesquelles
   sont des decisions editoriales du projet ?
6. Quels controles doivent empecher l'ecriture ou la soumission du XML ?

## Conclusion

Les deux notebooks melangent contrat XML, donnees de reference OntoME,
conventions CRM et DoReMus, heuristiques et erreurs techniques. Le remplacement
ne doit pas convertir ces comportements en code CLI par defaut. Il doit rendre
les sources d'autorite, les decisions et les exceptions explicites, versionnees
et verifiables.
