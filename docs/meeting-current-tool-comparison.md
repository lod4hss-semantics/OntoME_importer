# Ce que l'outil actuel fait, et ce qui manque encore

## Lecture rapide

L'outil actuel sait déjà lire un fichier RDF, signaler des problèmes, produire
un XML et garder une trace technique, lorsque les règles et données nécessaires
lui sont fournies. Il ne peut pas, à lui seul, décider quoi publier dans OntoME
ni trouver les informations officielles qui ne sont pas dans le fichier RDF.

Le travail à faire n'est donc pas de recommencer l'outil. Il faut d'abord lui
donner les bonnes règles, les bonnes données de référence et le bon processus
de validation.

Dans ce document, RDF désigne le format du fichier source, XML le fichier remis
à OntoME, et un espace OntoME (namespace) un ensemble de termes publiés
ensemble.

## Ce que l'outil actuel sait deja faire

| Besoin | Ce que l'outil fait aujourd'hui |
| --- | --- |
| Partir d'une source claire | Copie le fichier RDF dans un dossier de travail et en calcule l'empreinte. |
| Lire l'ontologie | Liste les ressources, liens, textes, langues, types de donnees et structures RDF. |
| Signaler les cas difficiles | Detecte les elements pris en charge, non pris en charge, incomplets ou ambigus. |
| Garder les informations source | Conserve les informations lues au lieu de les ignorer silencieusement. |
| Preparer des decisions | Produit un rapport et une revue locale guidée dans le terminal. |
| Produire un XML | Genere le XML seulement si les regles sont completes. |
| Verifier le resultat | Controle le XML, les identifiants, les liens externes et la coherence avec la source. |
| Rejouer un import | Vérifie les empreintes et peut reconstruire le même résultat, dans les cas couverts par ses règles et contrôles. |

## Ce que l'outil ne peut pas savoir seul

| Information manquante | Pourquoi l'outil ne peut pas l'inventer | Personne ou source attendue |
| --- | --- | --- |
| Namespace OntoME cible | C'est une decision de projet et de publication. | Projet OntoME et responsable editorial. |
| Version, libelle et description officiels | Ces informations peuvent ne pas etre presentes ou etre insuffisantes dans le RDF. | Proprietaire de l'ontologie. |
| ID OntoME de CRM 7.1.3 | Le registre OntoME versionné associe CRM 7.1.3 à l'ID 188. | Registre fourni par l'équipe OntoME. |
| ID exact d'un terme OntoME | Il est résolu depuis l'export RDF du namespace OntoME sélectionné. | API d'export du namespace. |
| Ce qui doit etre conserve | RDF/OWL contient parfois des informations que le XML ne represente pas directement. | Proprietaire de l'ontologie et OntoME. |
| Ce qui peut etre exclu | C'est un choix editorial avec des consequences. | Relecteur metier et responsable editorial. |
| Regle pour les datatypes | Les anciennes conversions CRM ne sont pas une regle officielle connue. | OntoME et experts CRM. |
| Procedure de publication | Elle depend des droits et du fonctionnement OntoME. | Administrateur et equipe OntoME. |

## Ecarts entre le besoin cible et l'outil actuel

| Sujet | Etat actuel | Ce qui est a faire |
| --- | --- | --- |
| Liste officielle OntoME | Le registre URI/version/ID fourni par l'équipe OntoME est livré avec l'outil ; l'API fournit les catalogues RDF de termes. | Définir le rythme de mise à jour du registre. |
| Choix humains | La revue terminale enregistre les décisions et leur journal local. | Définir qui confirme les décisions de publication. |
| Notes et exemples | L'outil demande une regle explicite pour les envoyer dans le bon champ XML. | Decider quels predicats RDF vont vers quels champs OntoME. |
| Règles indiquant combien de liens sont permis | L'outil actuel ne les produit pas. | Confirmer si elles sont nécessaires; définir source, règle et contrôles si oui. |
| Libellés des liens inverses | L'outil actuel garde le lien inverse si une règle le décrit, mais ne fabrique pas automatiquement son libellé. | Dire si ce libellé est obligatoire et d'où il vient. |
| Certains liens possibles dans le fichier XML | Le schéma XML peut les autoriser, mais l'outil ne les traite pas tous. | Choisir lesquels sont vraiment nécessaires au premier import pilote. |
| Verification apres publication | L'outil controle le fichier local, pas le resultat du serveur OntoME. | Definir les donnees disponibles apres soumission et la methode de comparaison. |
| Mises a jour de namespaces publies | Pas definies dans l'outil. | À laisser hors périmètre tant que la procédure OntoME n'a pas été confirmée. |

## Ce qu'il ne faut pas reprendre des notebooks

| Ancienne pratique | Pourquoi ne pas la reprendre |
| --- | --- |
| Choisir le premier ID OntoME trouve dans un fichier local | Le choix peut viser la mauvaise version. |
| Transformer silencieusement `xsd:string` en terme CRM | C'est une decision semantique qui doit etre approuvee. |
| Deviner les identifiants depuis les noms d'URI | Cette regle ne fonctionne pas pour toutes les ontologies. |
| Ecrire un XML malgre une erreur | Un resultat incorrect ne doit pas sembler pret a publier. |
| Mettre une information perdue dans un commentaire XML | Un commentaire ne signifie pas que l'information est importee dans OntoME. |
| Dependre de l'ordre des cellules Jupyter | Le meme import doit donner le meme resultat a chaque execution. |

## Ce que la reunion doit permettre de prioriser

Une fois les reponses obtenues, le travail pourra etre classe en trois groupes :

| Groupe | Contenu |
| --- | --- |
| Necessaire avant un essai LRMoo | Source officielle, namespace cible, CRM 7.1.3, liste OntoME, choix de conservation et controles bloquants. |
| Necessaire avant une publication reelle | Approbations, rapports de revue, dossier de soumission et verification apres import. |
| A traiter plus tard | Mises a jour de namespaces publies, automatisation serveur et prise en charge de constructions RDF/OWL non prioritaires. |

## Decision de produit a ne pas prendre trop tot

Le parcours utilisateur retenu est une revue locale dans le terminal. Les profils YAML restent des artefacts internes compilés. Son évolution dépend :

- des personnes qui prendront les decisions ;
- du nombre et du type de decisions a documenter ;
- du catalogue OntoME qui sera disponible ;
- de la procedure de validation et de publication confirmee.
