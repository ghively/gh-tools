# The v1 Vibe — pure-t2v painterly loop recipes (owner-canonized 2026-07-16)

The original 100-clip vibe library aesthetic: flowing, painterly, texture-like
abstract motion from PURE text-to-video (no still, no LoRA). The owner likes
this look in its own right — it is the ambient/mood instrument; FLF composed
subjects are the peaks. This file carries the COMPLETE recipe so any machine
with the plugin can reproduce or extend the set.

## Generation parameters (exact)
- `comfy_txt2video`: 768x512, 97 frames, 24fps, steps=25, cfg=3.0
- Prompt shape: `STATIC SHOT, no camera movement. <template with subject+palette>
  High contrast, bold graphic shapes, vivid saturated colors, VJ projection
  visual, sharp and clean, seamless looping motion.`
- Negative: `low quality, blurry, distorted, washed out, grey background,
  bright background, watermark`
- Loop finish: `comfy_loop_video` (forward-only crossfade). Never palindrome.
- On-host seed/prompt record: `/tank/projection-mapping/demos/manifest.json`

## neon
Template: Glowing neon {s} in vivid saturated {c} against a pure black void. The shapes pulse rhythmically and rotate slowly in place, holding a constant cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | wireframe tunnels | electric blue and hot orange | 11326522 |
| 01 | grid horizon | lime green and yellow | 3082752798 |
| 02 | concentric rings | crimson red and white | 3749881761 |
| 03 | sine waves | cyan and magenta | 210152485 |
| 04 | hexagon lattice | amber and emerald green | 682139679 |
| 05 | orbiting circuits | hot pink and ice blue | 1714413027 |
| 06 | spiral staircase | orange and teal | 308183095 |
| 07 | portal rings | scarlet and gold | 2015238103 |
| 08 | laser beams crossing | full rainbow spectrum | 3830595032 |
| 09 | wire mesh sphere | spring green and violet | 2677570702 |

## fractal
Template: An intricate glowing fractal {s} in vivid {c} against a pure black background. The whole pattern rotates slowly in place while its inner rings counter-rotate, breathing gently in a constant cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | mandala | fiery orange and gold | 3073286121 |
| 01 | spiral of spirals | emerald green and lime | 759170288 |
| 02 | branching tree | warm amber and crimson | 938611182 |
| 03 | crystalline snowflake | ice blue and white | 4063806734 |
| 04 | kaleidoscopic bloom | full rainbow spectrum | 558213331 |
| 05 | geometric web | scarlet and silver | 3918895969 |
| 06 | nested polygons | yellow and turquoise | 3719117981 |
| 07 | recursive vortex | hot pink and gold | 3925601401 |
| 08 | coral pattern | coral orange and sea green | 52952377 |
| 09 | labyrinth pattern | royal blue and copper | 1290778161 |

## particles
Template: Thousands of glowing {c} {s} drift and swirl against a pure black background. The particles circulate in a slow constant current, twinkling steadily as they move.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | dust particles | golden | 3993547126 |
| 01 | ember sparks | orange and red | 4078446238 |
| 02 | light orbs | warm white | 4059449137 |
| 03 | fireflies | yellow-green | 427783645 |
| 04 | glitter streams | silver and ice blue | 2372802998 |
| 05 | rising embers | crimson | 2195688315 |
| 06 | plankton motes | aqua green | 1095559666 |
| 07 | light specks | rainbow colored | 3306465443 |
| 08 | will-o-wisps | emerald green | 2965793601 |
| 09 | bokeh lights | amber and rose | 1274129536 |

## sacred
Template: A luminous sacred geometry {s} drawn in fine glowing {c} lines against a pure black background. The pattern rotates slowly and its rings counter-rotate in a constant hypnotic cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | mandala | golden | 3788935222 |
| 01 | flower of life | emerald and gold | 1153933122 |
| 02 | metatron cube | electric blue | 4129896334 |
| 03 | sri yantra | crimson and amber | 431222647 |
| 04 | geometric lotus | rose pink and white | 1927901994 |
| 05 | interlocking circles | copper and turquoise | 2548873156 |
| 06 | star tetrahedron | silver and violet | 795772700 |
| 07 | torus knot | orange and cyan | 2088790567 |
| 08 | hexagonal mandala | lime green and gold | 2776984431 |
| 09 | spiral sunburst | fiery red and yellow | 3752883176 |

## dissolve
Template: A glowing {c} {s} continuously sheds drifting luminous particles from its edges against a pure black background. The form holds steady while sparks stream upward and fade in a constant cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | human silhouette | white and blue | 774367245 |
| 01 | phoenix | fiery orange and red | 2991955178 |
| 02 | dancer figure | hot pink and violet | 2813940138 |
| 03 | tree | emerald green | 1278306358 |
| 04 | wolf | ice blue and silver | 4162418502 |
| 05 | rose flower | crimson and gold | 2103799823 |
| 06 | clock face | amber and copper | 2812267683 |
| 07 | violin | warm gold | 230595528 |
| 08 | butterfly | rainbow colored | 363455096 |
| 09 | chess king | white and scarlet | 4171368491 |

## water
Template: Flowing ribbons of luminous {c} {s} stream and ripple against a pure black background. The liquid circulates in a slow constant current, caustic light patterns shimmering steadily.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | water currents | deep blue and cyan | 3017245030 |
| 01 | liquid light | emerald and jade | 3896447273 |
| 02 | waves | turquoise and white foam | 891449231 |
| 03 | mercury | silver and chrome | 2247969253 |
| 04 | currents | sapphire and violet | 947494689 |
| 05 | ocean spray | aqua and seafoam green | 1870816064 |
| 06 | whirlpool | teal and gold | 485881381 |
| 07 | liquid glass | crystal clear and rainbow refractions | 1319703799 |
| 08 | bioluminescent tide | electric blue and green | 938230071 |
| 09 | waterfall | moonlit white and ice blue | 4051127260 |

## glass
Template: An ornate stained glass {s} glows with jewel tones of {c} against a pure black background. Light drifts across the panes in a slow constant sweep, colors shimmering in a steady cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | rose window | ruby, emerald and gold | 3017632156 |
| 01 | phoenix panel | flame orange, red and amber | 2088934573 |
| 02 | peacock window | teal, sapphire and emerald | 3244669728 |
| 03 | tree of life window | green, amber and sky blue | 3854947712 |
| 04 | celestial sun and moon panel | gold, silver and midnight blue | 4037996509 |
| 05 | koi fish panel | orange, white and water blue | 4210438751 |
| 06 | dragonfly window | iridescent green and violet | 873693439 |
| 07 | cathedral arch | crimson, cobalt and gold | 49087315 |
| 08 | lotus window | rose pink, jade and cream | 493291747 |
| 09 | hummingbird panel | emerald, magenta and turquoise | 1906996298 |

## ink
Template: Glowing {c} ink swirls like {s} in dark water against a pure black background. The ink billows and curls continuously in place, wisps circulating in a constant cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | a chrysanthemum | luminous white | 4177252973 |
| 01 | mountain mist | pale jade green | 1877074887 |
| 02 | a crane in flight | ivory and gold | 3015686031 |
| 03 | bamboo leaves | emerald green | 3671558580 |
| 04 | a swimming koi | orange and white | 2925247889 |
| 05 | storm clouds | electric blue and silver | 1472537778 |
| 06 | a curling dragon | crimson and gold | 1980154085 |
| 07 | cherry blossoms | rose pink and white | 630344408 |
| 08 | ocean waves | turquoise and foam white | 2929831878 |
| 09 | drifting smoke | violet and silver | 2537485622 |

## gold
Template: Ornate baroque {s} of glowing {c} metalwork against a pure black background. Light travels along the scrollwork curves in a continuous cycle, the metal shimmering steadily.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | filigree ornament | gold and ruby | 663227166 |
| 01 | picture frame | gold and emerald | 4275054896 |
| 02 | acanthus scrolls | rose gold and copper | 2256572387 |
| 03 | crown ornament | gold and sapphire | 3121249814 |
| 04 | mirror frame | silver and amethyst | 3551803884 |
| 05 | cherub relief | warm gold and ivory | 2980352946 |
| 06 | sunburst medallion | gold and fiery orange | 1834555585 |
| 07 | vine border | gold and jade green | 1807133678 |
| 08 | royal emblem | gold and crimson | 1516380077 |
| 09 | candelabra arms | brass and turquoise | 2806778138 |

## fire
Template: Swirling {s} of {c} rise against a pure black background. The flames flicker and dance in a slow constant rhythm, embers drifting upward in a steady cycle.

| # | subject | palette | seed |
|---|---|---|---|
| 00 | bonfire flames | orange and gold | 2175290621 |
| 01 | fire ribbons | electric blue flame | 1660825098 |
| 02 | flame vortex | emerald green fire | 2359719754 |
| 03 | phoenix wings of fire | crimson and amber | 3509339083 |
| 04 | candle flames | warm yellow and white | 1379642398 |
| 05 | fire rings | violet and magenta flame | 1548533656 |
| 06 | solar flares | white-hot gold | 458883004 |
| 07 | ember storms | deep red and orange | 2663323545 |
| 08 | flame serpents | teal and cyan fire | 3448207716 |
| 09 | burning rose | pink and scarlet flame | 2846308843 |
