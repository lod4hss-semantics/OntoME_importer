# Réunir les conditions d'un import OntoME fiable

## But de la réunion

Nous voulons remplacer d'anciens notebooks par un outil plus fiable. Avant de
developper davantage, il faut s'accorder sur ce que signifie "reussir un
import" dans OntoME.

Le sujet n'est pas seulement de produire un fichier XML. Il faut aussi savoir :

- quelle version de l'ontologie doit etre importee ;
- dans quel espace OntoME elle doit etre publiee ;
- comment relier ses termes aux termes OntoME existants ;
- quelles informations doivent etre conservees ;
- qui valide les choix avant publication.

## Mots utiles

| Mot | Sens simple |
| --- | --- |
| Ontologie | Le fichier qui décrit les classes, propriétés et liens d'un modèle de connaissance. |
| Espace OntoME (namespace) | Un ensemble de termes publiés ensemble dans OntoME. |
| URI | L'adresse unique qui identifie une ressource ou un terme. |
| XML | Le fichier structuré remis à OntoME pour l'import. |
| RDF/OWL | Les formats utilisés pour décrire l'ontologie source. |
| Empreinte | Un code calculé à partir d'un fichier, utile pour prouver qu'il n'a pas changé. |

## Situation actuelle

Les anciens notebooks savent lire une ontologie et fabriquer un fichier XML.
Ils ont rendu service pour des imports ponctuels, mais ils reposent sur des
regles cachees et des fichiers locaux anciens.

Exemples concrets :

- le notebook choisit des IDs OntoME depuis un fichier datant de 2022 ;
- il reconnait certains identifiants CRM uniquement parce que leurs noms suivent
  une forme particuliere ;
- il peut ecrire un XML meme si la verification du fichier signale une erreur ;
- certaines informations RDF sont ignorees, mises en commentaire ou modifiees
  sans decision explicite ;
- le resultat peut dependre de l'ordre dans lequel les cellules Jupyter ont ete
  executees.

Conclusion : les notebooks sont une source d'apprentissage, pas une base a
reproduire telle quelle.

## Ce que nous proposons

Un import doit suivre des etapes simples et visibles.

```text
1. Decider ce qui doit etre publie
2. Figer les fichiers de depart
3. Lire et lister tout ce que contient l'ontologie
4. Signaler ce qui pose question
5. Prendre les decisions avec les personnes competentes
6. Verifier les liens vers les termes OntoME existants
7. Produire un fichier XML de travail
8. Verifier le fichier et les decisions qui l'ont produit
9. Faire approuver, publier, puis verifier le resultat dans OntoME
```

Chaque etape doit laisser une trace lisible : ce qui a ete lu, ce qui a ete
decide, ce qui a ete exclu, et pourquoi.

## Ce que l'outil doit faire

L'outil doit aider l'equipe a :

- lire l'ontologie et signaler clairement les informations qu'il ne sait pas traiter ;
- lister clairement les classes, proprietes, notes, liens et cas difficiles ;
- montrer ce qui peut etre importe et ce qui demande une decision ;
- enregistrer les decisions et leur justification ;
- verifier les references a OntoME ;
- produire le XML seulement lorsque les conditions sont reunies ;
- garder le lien entre le XML final et les informations de depart ;
- produire un dossier complet pour la revue et l'archivage.

L'outil ne doit pas deviner seul un choix editorial ou semantique.

## Principaux risques a eviter

| Risque | Pourquoi c'est important | Reponse attendue |
| --- | --- | --- |
| Publier un fichier incorrect | Une fois publie, un import peut etre difficile a corriger. | Bloquer toute soumission quand un controle important echoue. |
| Utiliser le mauvais terme OntoME | Une relation peut pointer vers une mauvaise version du CRM. | Disposer d'une liste officielle et a jour des namespaces et termes OntoME. |
| Perdre des informations de l'ontologie | Notes, exemples, relations ou cardinalites peuvent disparaitre. | Dire explicitement ce qui doit etre garde, transforme ou ecarte. |
| Se fier a des conventions cachees | Une regle valable pour CRM peut etre fausse pour une autre ontologie. | Mettre les regles dans une configuration lisible et approuvee. |
| Ne pas pouvoir expliquer le resultat | Une erreur est difficile a revoir sans lien entre source et XML. | Garder les rapports et decisions avec le fichier final. |

## Cas LRMoo

Le fichier LRMoo analysé dans l'espace de travail déclare :

- LRMoo 1.1.1, novembre 2025 ;
- une dépendance vers CIDOC CRM 7.1.3.

Ces deux informations viennent du fichier source. Les éléments suivants restent
à confirmer avec OntoME :

Avant un essai d'import, il faut confirmer :

- quel espace OntoME correspond à CIDOC CRM 7.1.3 ;
- si l'ID `188` est bien celui à utiliser pour cette version ;
- comment obtenir les identifiants OntoME exacts des termes CRM utilises ;
- quels elements LRMoo doivent etre conserves ou traites autrement.

## Resultat attendu de la reunion

La reunion doit donner des reponses ou attribuer un responsable pour les sujets
suivants :

1. La source officielle a importer.
2. Le namespace OntoME cible et le type de publication.
3. Le schema XML officiel et la liste officielle des termes OntoME existants.
4. Les informations RDF/OWL qui doivent absolument etre conservees.
5. Les personnes qui approuvent les choix avant publication.
6. Les controles indispensables avant soumission.
7. La maniere de verifier le resultat apres publication.

## Documents de fond

- `legacy-notebook-analysis.md` : ce que fait le notebook RDF historique.
- `legacy-hardcoded-rules-register.md` : les regles cachees et donnees locales.
- `legacy-notebook-risks.md` : les risques classes par priorite.
- `target-import-workflow-and-reports.md` : la proposition complete de processus
  et de rapports.
