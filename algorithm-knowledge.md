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

# Connaissance algorithmique — régions bitmap 2D

Même plateforme et compilateur ; mesures détaillées dans
`quickdraw_regions_measurements.json`.

## Sous-ensemble 2D par runs horizontaux

- Problème : appliquer une opération uniquement aux pixels actifs sans scanner
  toute la bounding box.
- Précondition : runs triés, disjoints et groupés par scanline ; backend de
  copie efficace sur un run.
- Alternatives testées : masque bitmap complet (G0), transitions QuickDraw
  rejouées en masque de scanline (G2).
- Observé : `sparse_complex`, 36 runs et densité 0,7 %, prend 1,41 µs en G1
  contre 78,70/77,30 µs en G0/G2 ; stockage 4 440 octets. À 65 536 runs sur le
  damier, G1 atteint 772,15 µs et 528 440 octets, contre 188,09 µs et 65 576
  octets pour G0.
- Limite : le nombre de runs, pas la seule densité, gouverne dispatch et
  stockage. Chaque run entraîne ici un appel au backend R3.

## Région par changements entre scanlines

- Problème : stocker un contour dont de nombreuses scanlines successives se
  ressemblent.
- Technique : événements verticaux ordonnés et coordonnées horizontales qui
  XORent un état de scanline persistant ; provenance `PackRgn.a`, `SeekRgn.a`.
- Alternatives testées : masque 2D G0 et runs complets G1.
- Observé : le damier demande 2 090 octets en G2 malgré 65 536 runs, contre
  528 440 en G1 et 65 576 en G0. L'application G2 (190,82 µs) reste proche de
  G0 (188,09 µs), car les deux scannent un masque sur la bounding box dans ces
  réimplémentations portables.
- Limite : ce résultat valide la compacité, pas la performance exacte du code
  68000, dont la fusion par mots n'est pas reproduite instruction par
  instruction.

## Spécialisation d'une région rectangulaire

- Problème : ne pas payer l'encodage ni le parcours d'un contour lorsque la
  région est son rectangle englobant.
- Technique : bbox seule puis un appel au backend BitBlt ; provenance
  `Regions.a`, `RgnBlt.a`.
- Observé : G2 utilise 40 octets et applique le rectangle en 16,03 µs, contre
  65 576 octets et 111,55 µs pour le masque G0.
- Limite : le coût de détection est inclus dans la construction expérimentale ;
  QuickDraw peut connaître ce cas dès la représentation (`rgnSize = 10`).

## Construction contre réutilisation

- Problème : une représentation compacte ou éparse peut coûter plus cher à
  construire qu'un masque copié directement.
- Observé : sur `sparse_complex`, G0 gagne en usage unique estimé (333 µs
  contre 717 µs pour G1), mais G1 gagne après 100 usages (857 µs contre
  8 124 µs). Le même basculement apparaît sur `dense_complex` et `thin`.
- Substitution testée : G3 choisit rectangle, runs ou bitmap d'après le plus
  petit stockage exact. Elle évite l'explosion des runs sur le damier et garde
  leur application rapide ailleurs, mais son scan supplémentaire perd en usage
  unique. Le coût de construction doit donc rester une propriété de premier
  rang.

## Bounding box comme rejet, pas comme description de complexité

- Problème : éviter tout travail lorsque clip et destination sont disjoints et
  limiter la zone visitée autrement.
- Résultat fonctionnel : les 3 227 cas incluent une région non vide disjointe,
  des intersections partielles et des frontières irrégulières ; G0–G3
  préservent exactement les pixels hors intersection.
- Limite : à bounding box identique, `thin` et le damier ont des coûts très
  différents. Aire, runs et changements verticaux décrivent des dimensions
  distinctes ; aucun score unique n'est établi.
