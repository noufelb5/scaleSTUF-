# Ledgerwise SDR MVP

## Objectif et choix techniques

Livrer une application web pour que l'équipe commerciale puisse rechercher et qualifier des marques e-commerce américaines, contrôler les emails sortants, reprendre une conversation et voir les appels réservés. Le client Ledgerwise est fictif. Les 30 entreprises et les preuves de qualification sont réelles.

Le starter contient FastAPI et une page HTML. Pour le MVP, garder un seul service FastAPI avec des templates Jinja2, SQLAlchemy et Alembic. Utiliser SQLite pour le développement et PostgreSQL pour le déploiement. Brancher un LLM via des réponses JSON validées avec Pydantic. Utiliser une API email avec un environnement de test ou des boîtes contrôlées, puis un agenda dédié à la démo. Choisir un hébergeur qui permet HTTPS, une base persistante et au moins 14 jours de disponibilité après la remise. Réserver le choix des fournisseurs au premier test de bout en bout.

## Structure cible du repo

```text
app/
  main.py                 # Démarrage, configuration et routes
  models.py               # Entités persistantes
  schemas.py              # Entrées API et sorties LLM
  routes/
    dashboard.py          # Pages et actions de l'équipe commerciale
    webhooks.py           # Réponses entrantes du fournisseur email
  services/
    research.py           # Import des sources et extraction des preuves
    qualification.py      # Critères et score
    drafting.py           # Brouillons appuyés par les preuves
    replies.py            # Intention, règles et transfert humain
    email.py              # Envoi des messages approuvés
    calendar.py           # Disponibilités et réservation
  static/
  templates/
migrations/
tests/
  fixtures/               # Scénarios entrants anonymisés et sorties attendues
.env.example
README.md
HOW_I_WORKED.md
```

## Parcours et écrans

| Écran | Actions et données |
| --- | --- |
| Prospects | Importer une liste de domaines, lancer la recherche, trier par score et filtrer par statut |
| Fiche entreprise | Voir les critères, extraits, liens, date de consultation, contact et raison de le solliciter |
| File de validation | Voir les preuves associées au brouillon, modifier, approuver ou rejeter |
| Conversations | Voir l'historique, les décisions de l'agent, le statut et la reprise manuelle |
| Rendez-vous | Voir le prospect, le créneau, le fuseau et le lien vers l'événement |

## Données et règles métier

| Entité | Champs clés et contraintes |
| --- | --- |
| Company | Domaine unique, nom, secteur, pays, taille, CA, score et statut |
| Evidence | Entreprise, critère, URL, extrait, date de consultation et niveau de confiance |
| Contact | Entreprise, fonction, adresse si vérifiée, statut de contact |
| Thread | Contact, identifiant fournisseur, état et responsable |
| Message | Fil, direction, version, état de validation, preuves associées et identifiant fournisseur |
| Suppression | Adresse normalisée unique, motif et date |
| Booking | Fil, début et fin UTC, fuseau, identifiant agenda et état |
| AuditEvent | Acteur, action, date, entité et identifiant de corrélation |

- Dédupliquer les sociétés par domaine. Visiter en priorité les sites des marques, leurs pages carrière et leurs communiqués. Enregistrer les extraits qui soutiennent chaque critère. Autoriser une saisie manuelle pour compléter la collecte.
- Proposer un score initial sur 100 avec 40 points pour e-commerce US, 20 pour l'effectif, 20 pour le CA et 20 pour le signal récent. Montrer les détails du score. Une donnée introuvable reste inconnue. Indiquer le niveau de confiance et faire vérifier les profils aux critères essentiels incertains.
- Demander au LLM une sortie structurée contenant le brouillon et les identifiants des preuves. Contrôler que les preuves appartiennent à la bonne société et que chaque affirmation est soutenue lors de la revue.
- Passer les emails initiaux et les réponses générées par une file de validation. Les modifications créent une nouvelle version. La version approuvée est celle envoyée. Vérifier la liste de suppression et l'état du fil juste avant l'envoi.
- Traiter un refus ou une demande d'arrêt avant les autres intentions. Enregistrer le blocage durable, annuler les envois en attente et protéger les futurs imports. Détecter les questions de prix, les questions sur le bot, les objections, l'intérêt pour un appel et les demandes ambiguës. L'incertitude déclenche une reprise humaine.
- Authentifier les webhooks selon le fournisseur, dédupliquer les événements entrants par identifiant et conserver l'identifiant de chaque envoi. Pour une réponse dont le résultat d'envoi est incertain, réconcilier l'état auprès du fournisseur avant de réessayer.
- Proposer uniquement des créneaux libres dans un agenda réel. Afficher le fuseau du destinataire, revérifier la disponibilité à la confirmation, verrouiller le créneau au niveau de l'application et dédupliquer les confirmations. Si le créneau a été pris, proposer de nouvelles disponibilités.

## Contrats API à implémenter

| Route | Résultat attendu |
| --- | --- |
| POST /api/research | Import de domaines et lancement de la collecte |
| GET /api/companies | Liste filtrée avec scores et statut |
| GET /api/companies/{id} | Profil, contact et preuves |
| POST /api/companies/{id}/drafts | Créer un brouillon sourcé |
| PATCH /api/messages/{id} | Modifier la version en attente |
| POST /api/messages/{id}/review | Approuver ou rejeter une version précise |
| POST /api/messages/{id}/send | Envoyer la version approuvée avec contrôle de suppression |
| POST /webhooks/email/inbound | Traiter une réponse authentifiée et dédupliquée |
| POST /api/threads/{id}/takeover | Suspendre l'automatisation du fil |
| GET /api/threads/{id}/slots | Consulter les créneaux réels |
| POST /api/threads/{id}/bookings | Confirmer un créneau et retourner l'événement |

## Plan de réalisation sur 72 heures

| Temps écoulé | Travail | Critère de sortie |
| --- | --- | --- |
| H0–H4 | Vérifier l'heure de départ du délai. Ouvrir une session Codex dédiée et vérifier son export. Créer le repo, choisir les comptes de test et déployer un premier health check. | URL HTTPS accessible et premier test de connectivité email et agenda effectué |
| H4–H12 | Mettre en place les modèles et migrations. Construire un parcours complet sur une vraie entreprise et une boîte de test. | Une preuve affichée, un score expliqué, un brouillon validé, une réponse reçue et un événement visible dans l'agenda |
| H12–H28 | Collecter et vérifier au moins 30 entreprises réelles. Ajouter recherche, filtre, preuves et revue des brouillons dans le dashboard. | Au moins 30 dossiers réels avec sources, et un brouillon par dossier qualifié |
| H28–H44 | Finaliser les webhooks, la suppression durable, la reprise humaine et les créneaux. | Les scénarios refus, prix, bot, ambiguïté et réservation fonctionnent de bout en bout |
| H44–H56 | Terminer l'interface, protéger l'accès démo, tester la persistance après redémarrage et mesurer les résultats. | Parcours complet reproductible depuis une session privée sur l'URL publique |
| H56–H64 | Générer et relire HOW_I_WORKED.md, exporter les sessions et enregistrer la démo. | Liens, résultats de tests, coûts, limites et vidéo prêts |
| H64–H72 | Vérifier la disponibilité, les droits d'accès, la lecture du Loom et les pièces de remise. Envoyer dès que le dossier est prêt. | Réponse envoyée avant l'échéance, avec une marge pour les problèmes de dernière minute |

## Vérifications à mesurer

| Scénario | Résultat attendu |
| --- | --- |
| Aucun élément sur le CA | Indicateur inconnu visible et aucune affirmation inventée |
| Source contradictoire ou douteuse | Revue humaine requise |
| Brouillon modifié après approbation | Nouvelle validation nécessaire |
| Email rejeté | Aucun envoi |
| « Not interested » ou « unsubscribe » | Blocage persistant, même après réimport ou envoi déjà en file |
| Question tarifaire | Proposition d'en parler lors d'un appel |
| « Are you a bot? » | Réponse honnête |
| Message ambigu ou objection inconnue | Conversation transférée à un humain |
| Double webhook | Un seul traitement |
| Deux confirmations sur le même créneau | Une seule réservation |
| Créneau pris après proposition | Nouvelle liste de créneaux |
| Démo ouverte dans une session privée | Accès, navigation, preuve, approbation et rendez-vous vérifiés |

Créer un jeu de scénarios reproductibles et relever le nombre de réussites sur le nombre de cas exécutés pour le tri des réponses, la suppression et les réservations. Pour la qualité des emails, vérifier manuellement la correspondance entre faits et sources sur un échantillon et consigner la taille de l'échantillon. Mesurer les coûts observés ou calculés avec les hypothèses explicites.

## Démo et remise

Enregistrer une vidéo Loom de moins de 10 minutes. Viser 8 minutes. Présenter le dashboard comme à l'équipe commerciale de Ledgerwise, idéalement en anglais puisque le brief est en anglais.

| Minute | Démo |
| --- | --- |
| 0–1 | Tableau des prospects et filtre |
| 1–3 | Fiche d'une entreprise réelle, score, preuves et brouillon |
| 3–5 | Modification, validation, envoi vers une boîte de test et traitement d'une réponse |
| 5–7 | Créneaux réels et événement créé, puis exemple de blocage ou reprise humaine |
| 7–8 | Résultats mesurés, coût et limites du MVP |

Répondre à l'email d'origine avec l'URL de l'application et l'accès démo si nécessaire, le lien GitHub public, l'export intégral non édité des sessions IA du cas, HOW_I_WORKED.md et le lien Loom. Garder l'application accessible deux semaines après la remise.

Dès H0, utiliser des sessions dédiées à ce cas et tenir les clés et données privées hors du code, des prompts et des captures. Dans HOW_I_WORKED.md, noter les outils choisis et abandonnés et leurs raisons, le plan et ses changements, les consignes données à l'IA, les erreurs observées, les tests chiffrés, les coûts et ce que tu ferais avec plus de temps. Générer ce fichier à la fin à partir de tes notes et le relire avant l'envoi.
