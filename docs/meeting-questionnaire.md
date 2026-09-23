# Questions pour la réunion OntoME

## Utilisation

Cette liste sert a obtenir des decisions, pas a discuter du code. Pour chaque
question, noter : la reponse, la personne qui la confirme, la source qui fait
foi et les actions a faire ensuite.

Les mots techniques inévitables sont employés au sens suivant : une URI est
l'adresse unique d'un terme; un espace OntoME (namespace) est un ensemble de
termes publiés ensemble; XML est le fichier remis à OntoME; RDF/OWL est le
format de l'ontologie source; XSD est la règle qui décrit la forme attendue du
fichier XML.

## 1. Ce qui doit etre importe

| Question | Reponse attendue | Pourquoi cette reponse est necessaire |
| --- | --- | --- |
| Quel fichier est la source officielle ? | URL ou fichier, format, version et date. | Pour que tout le monde travaille sur le meme contenu. |
| Qui confirme cette source ? | Nom ou role. | Pour savoir qui contacter si une information est absente ou incorrecte. |
| L'import concerne-t-il un nouveau namespace, une nouvelle version, ou une mise a jour ? | Un choix clair. | Les trois cas ne suivent peut-etre pas la meme procedure. |
| Quelle URI et quel libelle doivent etre publies ? | Valeurs approuvees, dans les langues utiles. | Ces informations ne peuvent pas etre devinees depuis le RDF. |
| Quelle version, date, description et liste de contributeurs doivent apparaitre ? | Valeurs editees et leur source. | Pour publier des metadonnees correctes. |

## 2. Droits et publication

| Question | Reponse attendue | Pourquoi cette reponse est necessaire |
| --- | --- | --- |
| Quel projet OntoME porte l'import ? | Nom et URL du projet. | Pour identifier le bon espace de travail. |
| Qui a le droit de soumettre l'import ? | Nom ou role. | Selon la documentation OntoME transmise, ce droit est réservé aux administrateurs du projet; à confirmer pour ce projet. |
| Quel est le circuit de validation avant la soumission ? | Personnes, ordre et preuve attendue. | Pour ne pas publier un fichier non revu. |
| Que se passe-t-il si un import publie comporte une erreur ? | Procedure officielle de correction. | La documentation OntoME transmise indique qu'un namespace importé est publié et non modifiable; à confirmer avec l'équipe OntoME. |
| Peut-on tester l'import avant publication ? | Environnement, namespace de test ou autre procedure. | Pour diminuer le risque sur un import reel. |

## 3. References vers OntoME existant

| Question | Reponse attendue | Pourquoi cette reponse est necessaire |
| --- | --- | --- |
| Quel namespace OntoME represente CIDOC CRM 7.1.3 ? | ID OntoME, URL et libelle/version. | Le fichier LRMoo analysé déclare une dépendance vers CRM 7.1.3. |
| L'ID `188` correspond-il actuellement a CRM 7.1.3 ? | Oui/non, avec preuve. | L'ancien fichier local associait 188 a CRM 7.1.1. |
| Ou obtenir la liste officielle des namespaces OntoME ? | URL, export ou API. | Le fichier local actuel date de 2022. |
| Ou obtenir les identifiants exacts des termes OntoME ? | URL, export ou API, avec format. | Un ID de namespace ne suffit pas pour viser un terme precis. |
| Comment identifier la version d'un namespace OntoME ? | Regle officielle. | Plusieurs versions du CRM peuvent exister. |
| Comment sont signales les namespaces anciens ou interdits ? | Regles et source d'information. | Pour ne pas creer de lien vers une reference non autorisee. |

## 4. Informations a conserver

| Question | Reponse attendue | Pourquoi cette reponse est necessaire |
| --- | --- | --- |
| Quels liens entre termes doivent etre conserves ? | Liste priorisee, par exemple parent, équivalent, inverse. | Certains liens RDF/OWL ne se traduisent pas automatiquement. |
| Les règles indiquant combien de liens sont permis doivent-elles être importées ? | Oui/non, et règle de représentation. | Les anciens notebooks traitaient ces cardinalités de manière fragile. |
| Comment traiter les notes, exemples et texte HTML ? | Regle claire de conservation, nettoyage ou exclusion. | Les anciens notebooks perdaient ou modifiaient certains textes. |
| Comment traiter les types de valeurs, comme texte ou nombre ? | Table de correspondance approuvée ou instruction d'exclusion. | Les anciens notebooks faisaient des conversions cachées vers CRM. |
| Comment traiter les structures RDF/OWL plus complexes, comme restrictions, listes ou unions ? | Importer, transformer, exclure ou bloquer. | Sans décision, une partie de l'ontologie peut disparaître. |
| Une exclusion est-elle acceptable ? | Conditions, justification et approbateur. | Pour que toute perte soit visible et assumee. |

## 5. Verifications et rapports

| Question | Reponse attendue | Pourquoi cette reponse est necessaire |
| --- | --- | --- |
| Quel schema XML est officiel aujourd'hui ? | Fichier ou URL, version et date. | Notre analyse traite le XSD local du dépôt comme une copie historique; son statut doit être confirmé. |
| Quels controles doivent empecher toute soumission ? | Liste de blocages. | L'outil doit savoir quand s'arreter. |
| Quels rapports OntoME veut-il avant une soumission ? | Liste et format. | Pour produire des documents utiles, sans travail inutile. |
| Quel niveau de detail faut-il pour expliquer le XML ? | Exemple ou regle. | Pour faciliter la revue et le support. |
| Peut-on comparer le resultat publie avec le XML soumis ? | Methode et donnees accessibles. | Pour verifier que l'import a produit le resultat attendu. |

## 6. Resultat a noter en fin de reunion

| Sujet | Decision ou action | Responsable | Source/preuve | Echeance `[A confirmer]` |
| --- | --- | --- | --- | --- |
| Source officielle |  |  |  |  |
| Namespace cible |  |  |  |  |
| CRM 7.1.3 dans OntoME |  |  |  |  |
| Catalogue namespaces/termes |  |  |  |  |
| Schema XML officiel |  |  |  |  |
| Informations a conserver |  |  |  |  |
| Procedure de validation |  |  |  |  |
| Procedure de correction |  |  |  |  |
| Prochain essai pilote |  |  |  |  |
