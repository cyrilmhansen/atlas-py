# Connaissance algorithmique — QuickDraw BitBlt copie

Plateforme mesurée : AMD Ryzen AI 9 HX 370, x86-64 Linux, GCC 16.1.1 `-O3`,
un cœur logique, glibc 2.44. Les débits sont utiles et cache-hot ; ils ne
représentent pas la totalité du trafic mémoire.

## Copie de bloc bitmap non aligné

- Problème : copier une suite de bits dont les origines source et destination
  n'ont pas le même alignement, tout en préservant les bits de bord.
- Techniques comparées : blocs génériques 32 bits (R1), reconstruction en mots
  16 bits inspirée de QuickDraw (R2), blocs 64 bits (R3).
- Préconditions : rectangles valides de même étendue dans cette API portable ;
  lecture bornée à chaque ligne.
- Conséquences observées (`misaligned_large`) : R1 effectue 506 880 itérations,
  R2 994 080, R3 261 120. Les médianes sont respectivement 6,737 / 7,649 /
  6,906 ms. Une unité plus large réduit les itérations, mais R3 ne gagne pas
  ici sur R1 ; aucune cause microarchitecturale supplémentaire n'est établie.
- Ouvert : meilleur chargement borné de mots adjacents, sensibilité aux tailles
  et à une autre plateforme.

## Parcours directionnel pour copie chevauchante

- Problème : ne pas écraser les bits source avant leur lecture.
- Technique : choisir bas-vers-haut lorsque la destination est plus basse, ou
  droite-vers-gauche sur une même ligne déplacée à droite.
- Alternative comparée : snapshot compact complet (R1).
- Conséquences observées (`scroll_overlap`) : R1 réserve jusqu'à 15 360 octets
  temporaires et prend 12,988 ms ; R2/R3 n'allouent rien et prennent 7,924 /
  7,027 ms. Les quatre variantes restent bit-identiques.
- Provenance historique : `BitBlt.a:162-193,280-297`.
- Ouvert : aliasing entre descripteurs distincts partageant une allocation ; le
  source historique ne le détecte pas et l'API expérimentale ne le promet pas.

## Chemin spécialisé de copie alignée

- Problème : retirer reconstruction, masques intérieurs et branches de la
  boucle chaude lorsque les bits copiés forment des octets complets.
- Techniques : mots 32 bits génériques (R1), mots 16 bits avec chemin aligné
  inspiré de QuickDraw (R2), `memmove` ligne par ligne (R3).
- Précondition R3 : origines et largeur alignées sur huit bits ; sens vertical
  conservé entre les lignes en cas de chevauchement.
- Conséquences observées (`aligned_large`) : 6,088 ms / 1,642 ms / 0,037 ms,
  soit 0,301 / 1,115 / 49,880 GiB/s utiles. R3 délègue 1 966 080 octets à
  `memmove`; ce résultat cache-hot ne doit pas être interprété comme bande
  passante DRAM.
- Provenance historique : le fast path mode 0, shift nul est sélectionné hors
  boucle dans `BitBlt.a:300-314,390-443`.
- Ouvert : comportement sur working sets froids et autres libc/CPU.

## Masques de bord

- Problème : préserver les bits extérieurs au rectangle, notamment pour les
  largeurs 1, 15/16/17, 31/32/33 et 63/64/65.
- Technique : premières/dernières unités partielles ; le source historique
  combine les masques quand tout tient dans un mot.
- Résultat : 6 298 cas déterministes, dont 5 000 pseudo-aléatoires et plusieurs
  directions de chevauchement, sont identiques bit à bit pour R0–R3 ; les
  gardes mémoire et ASan/UBSan restent intacts.
- Ouvert : autres modes de combinaison et clipping, hors périmètre.

## Perspective historique

- Structurellement encore pertinent : masques de bord, reconstruction
  désalignée, choix du sens de parcours, spécialisation alignée et dispatch hors
  boucle chaude.
- Probablement lié au 68000 : mots naturels de 16 bits, reconstruction précise
  par lecture longue 32 bits décalée, boucle de copie déroulée par saut dans une
  table de 32 mots longs.
- Indéterminé : bénéfice exact du déroulage original sur un 68000 réel et
  compromis de taille du code ; aucun environnement 68000 n'a été reconstruit.
