# DTE v1.0 — Audit Technique Complet
# Deriv Trading Ecosystem — Documentation Intégrale

**Projet** : thMonster_v2_Top  
**Version** : DTE v1.0  
**Date** : 2026-06-17  
**Broker** : Deriv.com Limited — Compte Demo (Login : 201797413, Serveur : Deriv-Demo)  
**Langage** : Python 3.12  
**GitHub** : https://github.com/jino67/th_monster_with_claude.git

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Les 8 actifs synthétiques](#2-les-8-actifs-synthétiques)
3. [Architecture du système](#3-architecture-du-système)
4. [Flux de données — de MT5 au signal](#4-flux-de-données--de-mt5-au-signal)
5. [Modèle A — Streak Analyser](#5-modèle-a--streak-analyser)
6. [Modèle B — Volatility Cycle Detector](#6-modèle-b--volatility-cycle-detector)
7. [Modèle C — Event Detector](#7-modèle-c--event-detector)
8. [Modèle D — Monte Carlo Engine](#8-modèle-d--monte-carlo-engine)
9. [Modèle E — Legacy Adapter](#9-modèle-e--legacy-adapter)
10. [Fusion des signaux — Score composite](#10-fusion-des-signaux--score-composite)
11. [LLM Advisor](#11-llm-advisor)
12. [Gestion des positions — Sizing, SL, TP](#12-gestion-des-positions--sizing-sl-tp)
13. [MT5 Data Provider — Exécution des ordres](#13-mt5-data-provider--exécution-des-ordres)
14. [API FastAPI](#14-api-fastapi)
15. [Extension Chrome](#15-extension-chrome)
16. [Modes de fonctionnement](#16-modes-de-fonctionnement)
17. [Règles absolues du système](#17-règles-absolues-du-système)
18. [Structure des fichiers](#18-structure-des-fichiers)
19. [Guide de lancement](#19-guide-de-lancement)

---

## 1. Vue d'ensemble

Le DTE (Deriv Trading Ecosystem) est un bot de trading algorithmique conçu exclusivement pour les **indices synthétiques Deriv** (actifs RNG certifiés). Il ne passe jamais par l'API WebSocket Deriv — toutes les données et tous les ordres transitent uniquement par la librairie Python **MetaTrader5**.

Le système repose sur un **signal composite calculé par 5 modèles indépendants** fusionnés en un score de 0 à 100. Ce score pilote la décision de trading, la taille de position, et les niveaux de stop-loss et take-profit.

**Principe fondamental** : chaque modèle donne un avis indépendant. La fusion réduit le bruit et n'agit que lorsqu'un consensus se dégage. Un seul modèle ne peut jamais déclencher un trade seul.

---

## 2. Les 8 actifs synthétiques

| Actif MT5 | Code Deriv | Type | Comportement |
|---|---|---|---|
| Volatility 100 Index | R_100 | Volatilité | Mouvement continu, 100% volatilité simulée |
| Volatility 100 (1s) Index | 1HZ100V | Volatilité | Même que Vol 100 mais tick toutes les secondes |
| Crash 500 Index | CRASH500 | Spike | Spike baissier brutal toutes ~500 bougies M1 |
| Crash 1000 Index | CRASH1000 | Spike | Spike baissier brutal toutes ~1000 bougies M1 |
| Boom 500 Index | BOOM500 | Spike | Spike haussier brutal toutes ~500 bougies M1 |
| Boom 1000 Index | BOOM1000 | Spike | Spike haussier brutal toutes ~697 bougies M1 |
| Step Index | stpRNG | Step | Mouvements en paliers réguliers de ±0.1 |
| Range Break 100 Index | RB100 | Range | Breaks de range aléatoires, longues périodes plates |

**Important** : ces actifs sont générés par RNG certifié. Il n'y a pas de manipulations humaines, pas de news, pas de liquidité à chercher. Les patterns statistiques sont stables et exploitables.

---

## 3. Architecture du système

```
┌─────────────────────────────────────────────────────────────────┐
│                     MetaTrader 5 (terminal)                      │
│   Données OHLCV M1/M5/M15/H1  ←→  Exécution des ordres          │
└────────────────────────┬────────────────────────────────────────┘
                         │ MetaTrader5 (lib Python)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MT5DataProvider                               │
│  get_candles() / get_all_timeframes() / place_order()            │
│  compute_sl_tp_dynamic() / calculate_volume()                    │
└──┬─────────┬──────────┬──────────┬──────────┬───────────────────┘
   │         │          │          │          │
   ▼         ▼          ▼          ▼          ▼
Modèle A  Modèle B  Modèle C  Modèle D  Modèle E
Streaks   Volatilité  Événement Monte     Legacy
(0.30)    (0.20)    (0.20)    Carlo     Adapter
                              (0.15)    (0.15)
   │         │          │          │          │
   └─────────┴──────────┴──────────┴──────────┘
                         │
                         ▼
               ┌──────────────────┐
               │  SignalFusion    │
               │  Score 0-100     │
               │  Direction ±1    │
               │  Alignement      │
               └────────┬─────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
            ▼                       ▼
    Score 40-65 ?              Score ≥ 40 + direction
            │                       │
            ▼                       ▼
     LLMAdvisor              MoneyManager
  (Claude Haiku /             SL/TP dynamiques
   GPT-4o-mini)               Volume en lots
            │                       │
            └───────────┬───────────┘
                        │
                        ▼
                  MT5DataProvider
                  place_order()
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
        FastAPI :8000        Chrome Extension
        /api/full_state       overlay deriv.com
```

---

## 4. Flux de données — de MT5 au signal

**Fréquence** : toutes les 2 secondes (paramètre `LOOP_SLEEP_SEC = 2`)

**Pour chaque symbole à chaque cycle** :

```
1. MT5DataProvider.get_all_timeframes(symbol)
   → M1  : 200 bougies (priorité — décisions court terme)
   → M5  : 150 bougies (contexte moyen terme)
   → M15 : 100 bougies (structure)

2. MT5DataProvider.get_candles(symbol, 'H1', count=60)
   → H1 : 60 bougies pour le Modèle E (Price Action structure)
   → Si H1 indisponible : synthétisé depuis M15 via resample('1h')

3. Les 5 modèles calculent en parallèle (séquentiel en Python)
   → Chacun retourne un score [0-100] et parfois une direction

4. SignalFusion.compute() fusionne les 5 scores
   → Score composite pondéré
   → Consensus directionnel A+E
   → Bonus d'alignement multi-TF

5. Si score borderline (40-65) et symbole actif : LLMAdvisor.advise()

6. Si FULL_AUTO + signal valide : _execute_trade()

7. État mis à jour → FastAPI state → WebSocket → Chrome Extension
```

---

## 5. Modèle A — Streak Analyser

**Fichier** : `engine/streak_analyser.py`  
**Poids dans le composite** : **0.30** (le plus important)

### Principe

Analyse les séquences consécutives de bougies haussières ou baissières sur 3 timeframes. Chaque séquence ("streak") est associée à une **probabilité conditionnelle empirique** extraite des données historiques réelles.

### Calcul du streak

```python
def compute_streak(candles):
    # Parcourt les bougies de droite à gauche
    # Compte les corps dans la même direction
    # S'arrête dès qu'une bougie change de sens
    # Retourne (streak_value, longueur)
    # streak_value > 0 = séquence UP
    # streak_value < 0 = séquence DOWN
```

Exemple : 5 bougies UP consécutives → streak = +5

### Probabilités conditionnelles empiriques (extrait)

Ces probabilités ont été mesurées sur des données historiques réelles.

**Crash 500 Index M1** :
| Streak UP | P(suivante UP) | Interprétation |
|---|---|---|
| 1 | 90.8% | Quasi-certain de continuer UP |
| 5 | 88.6% | Toujours très probable |
| 10 | 88.9% | Stable sur longue séquence |

**Boom 500 Index M1** :
| Streak DOWN | P(suivante DOWN) | Interprétation |
|---|---|---|
| 1 | 91.9% | La tendance baissière continue |
| 5 | 89.0% | Persistance forte |
| 10 | 87.5% | Toujours valide |

**Volatility 100 Index M1** :
| Streak UP | P(suivante UP) | Interprétation |
|---|---|---|
| 1 | 50.1% | Aléatoire — aucun edge |
| 3 | 45.7% | Légère mean-reversion |
| 5 | 64.4% | Momentum court terme |

**Remarque** : sur Crash/Boom, les streaks UP (Crash) ou DOWN (Boom) ont une persistance extrêmement forte (88-96%) due à la nature RNG qui génère des séquences directionnelles entre les spikes. Sur Volatility, les probabilités restent proches de 50% — aucun edge fort.

### Score du Modèle A

```
Pour chaque timeframe (M1, M5, M15) :
  raw_score = (prob - 50.0) × 2.0 × direction
  # prob > 50 + direction = continuation probable → score positif
  # prob < 50 + direction = retournement probable → score négatif

Composite = raw_M1 × 0.50 + raw_M5 × 0.30 + raw_M15 × 0.20

Bonus alignement :
  3 TF même direction → × 1.25
  2 TF même direction → × 1.10

Score final = 50.0 + composite  (normalisé [0, 100])
```

**Poids par timeframe** : M1 = 50%, M5 = 30%, M15 = 20%

---

## 6. Modèle B — Volatility Cycle Detector

**Fichier** : `engine/volatility_detector.py`  
**Poids dans le composite** : **0.20**

### Principe

Détecte la **phase de volatilité courante** sur chaque timeframe : compression (énergie qui s'accumule), expansion (mouvement en cours), ou transition. Favorise les entrées en phase d'expansion.

### Calcul de l'ATR

```python
def calculate_atr(df, window=14):
    # ATR simplifié pour synthétiques RNG (pas de gap overnight)
    # = moyenne des ranges (high - low) sur 14 périodes
    return df.tail(window)['range'].mean()
```

### Seuils de phase (calibrés par actif)

**Crash 500 Index** :
| Timeframe | Compression (ATR <) | Expansion (ATR >) |
|---|---|---|
| M1 | 0.45 | 0.85 |
| M5 | 2.00 | 3.50 |
| M15 | 4.00 | 8.00 |

**Range Break 100 Index** (mouvements naturellement plus larges) :
| Timeframe | Compression | Expansion |
|---|---|---|
| M1 | 8.00 | 16.00 |
| M5 | 20.00 | 40.00 |
| M15 | 35.00 | 65.00 |

### Score de phase

| Phase | Score |
|---|---|
| Expansion | 75.0 — favorable, momentum en cours |
| Transition | 50.0 — neutre, attendre confirmation |
| Compression | 25.0 — défavorable, énergie accumulée mais direction inconnue |

### Score composite du Modèle B

```
Score_B = score_M1 × 0.50 + score_M5 × 0.35 + score_M15 × 0.15
```

**Poids** : M1 = 50%, M5 = 35%, M15 = 15%  
**Interprétation** : si les 3 TF sont en expansion → score = 75. Ce modèle ne donne pas de direction, il mesure la "qualité" du contexte de marché.

---

## 7. Modèle C — Event Detector

**Fichier** : `engine/event_detector.py`  
**Poids dans le composite** : **0.20**

### Principe

Spécifique aux actifs **Crash et Boom**. Calcule la probabilité qu'un spike se produise prochainement, en utilisant une loi exponentielle calibrée sur les intervalles réels entre spikes.

Pour les autres actifs (Volatility, Step, Range Break), le score est fixé à **50 (neutre)** — ce modèle n'apporte pas d'information les concernant.

### Paramètres calibrés

| Actif | Intervalle moyen λ | Amplitude moyenne | Direction |
|---|---|---|---|
| Crash 500 Index | 747 ticks | 4.88 points | Baissier (-1) |
| Crash 1000 Index | 5000 ticks | 6.33 points | Baissier (-1) |
| Boom 500 Index | 449 ticks | 6.48 points | Haussier (+1) |
| Boom 1000 Index | 697 ticks | 14.72 points | Haussier (+1) |

### Loi exponentielle

```
P(spike dans les N prochains ticks) = (1 - e^(-N/λ)) × 100

Exemple Crash 500 (λ=747) :
  Après 200 ticks depuis dernier spike : P = 23.4%
  Après 500 ticks : P = 49.0%
  Après 747 ticks : P = 63.2% (= 1 - 1/e)
  Après 1500 ticks : P = 86.5%
```

### Détection de spike récent

```python
# Un spike vient de se produire si :
# - Range de la dernière bougie M1 > 3 × ATR moyen(20)
# - Body dans la bonne direction (négatif pour Crash, positif pour Boom)
# → Remet le compteur à 0
```

### Niveaux d'alerte

| Probabilité | Niveau | Action |
|---|---|---|
| ≥ 80% | CRITIQUE | Notification Chrome, log WARN |
| 60-79% | HAUTE | Log WARN |
| 40-59% | MOYENNE | Log INFO |
| < 40% | FAIBLE | Normal |

### Score du Modèle C

```
Score_C = min(90, prob_imminent)
# Plafonné à 90 — jamais 100 pour éviter une surpondération
# Pour non-Crash/Boom : Score_C = 50 (neutre)
```

**Utilisation clé** : si `spike_alert = True` (spike détecté dans la dernière bougie), le TP est réduit automatiquement (RR 1.2) pour prendre le profit avant la correction post-spike.

---

## 8. Modèle D — Monte Carlo Engine

**Fichier** : `engine/monte_carlo.py`  
**Poids dans le composite** : **0.15**

### Principe

Lance N simulations indépendantes de séquences de bougies futures, basées sur les statistiques observées récemment sur M1. Retourne la probabilité que le bilan soit positif sur un horizon de 10 bougies.

### Calcul des statistiques empiriques

```python
# Depuis les 200 dernières bougies M1 :
win_rate = nb_bougies_positives / total
avg_up   = moyenne des corps haussiers
avg_down = moyenne des corps baissiers (valeur absolue)
```

### Simulation

```python
# Pour chaque simulation (500 par défaut) :
# Génère 10 nombres aléatoires [0, 1]
# Si random < win_rate → +avg_up, sinon -avg_down
# Somme le PnL sur les 10 étapes

prob_positive = % de simulations avec PnL final > 0
score_D = prob_positive  # [0-100]
```

### Sortie du Modèle D

- `score` : probabilité d'être positif sur 10 bougies
- `expected_value` : espérance de gain par simulation
- `ci_5_95` : intervalle de confiance à 90% (percentiles 5 et 95)
- `win_rate_empirical` : win rate mesuré sur M1 récent

**Rôle dans le système** : apporte une dimension probabiliste indépendante des patterns directionnels. Si les statistiques récentes sont défavorables, ce modèle pèse contre le trade.

---

## 9. Modèle E — Legacy Adapter

**Fichier** : `engine/legacy_adapter.py`  
**Poids dans le composite** : **0.15**

### Principe

Intègre l'ancien écosystème de trading (Price Action SMC, EMA/ATR, MarketRegimeDetector) comme 5ème modèle. C'est le seul modèle qui lit la **structure de marché technique**.

**Dégradation gracieuse** : si n'importe quelle partie du code legacy plante, le score E revient à 50 (neutre) sans bloquer le système.

### Routage par type d'actif

| Actif | Stratégie utilisée |
|---|---|
| Crash 500, Crash 1000, Boom 500, Boom 1000 | `CrashBoomStrategy` V5 |
| Volatility 100, Volatility 100 (1s), Step Index, Range Break 100 | `VolatilityStrategy` |

### CrashBoomStrategy V5 — "Smart Money Reversal"

Logique de reversal : **vendre avant le spike sur Boom, acheter avant le spike sur Crash**.

**Critères de scoring** (total 100 points) :

| Critère | Points max | Description |
|---|---|---|
| Structure H1 alignée | +15 | BEARISH_STRUCTURE pour Boom, BULLISH pour Crash |
| Contre-tendance H1 | -20 | Pénalité si on trade contre le trend fort |
| Zone FVG H1 (Fair Value Gap) | +15 | Prix dans une FVG H1 dans la bonne direction |
| Structure M15 alignée | +30 | BEARISH/BULLISH_STRUCTURE ou COMPRESSION +15 |
| Zone FVG M5 | +30 | Prix dans une FVG M5 dans la bonne direction |
| Momentum M1 | +10 | Confirmation court terme |

**Sortie** : `action` (BUY/SELL/HOLD) + `confidence_score` [0.0 – 1.0]

### VolatilityStrategy — EMA/ATR/Structure

Pour les actifs de type volatilité pure.

**Filtre obligatoire** : ATR M5 < 50 points → HOLD immédiat (marché trop plat)

**Critères** :
- Trend H1 : EMA 50 + structure BULLISH/BEARISH_STRUCTURE
- FVG H1 et M5 comme zones d'entrée
- RSI M5 pour confirmation momentum

### PriceActionAnalyzer (SMC Lite)

Utilisé par les deux stratégies. Calcule :
- **Fractals** : hauts et bas locaux sur 5 bougies (fenêtre centrée)
- **VWAP** : prix moyen pondéré par le volume (ou SMA 20 en fallback)
- **Structure** : séquences HH/HL → BULLISH_STRUCTURE, LH/LL → BEARISH_STRUCTURE, autre → COMPRESSION/RANGING
- **FVG (Fair Value Gaps)** : imbalances de prix — zones vides entre les bougies qui agissent comme aimants

### MarketRegimeDetector

Appliqué en couche supplémentaire sur le score legacy. Analyse M1+M5+M15 et classe le marché.

| Régime | Multiplicateur | Effet sur score E |
|---|---|---|
| TRENDING_MARKET | × 1.10 | Amplifie les signaux directionnels |
| VOLATILE_MARKET | × 0.75 | Réduit la confiance (mouvement chaotique) |
| RANGING_MARKET | × 0.85 | Atténue légèrement |
| NEUTRAL_MARKET | × 0.90 | Légère atténuation |
| MIXED_MARKET | × 0.65 | Forte atténuation (signal peu fiable) |

### Conversion en score DTE

```python
score = 50.0 + direction × confidence × 50.0
# confidence = 1.0, direction = +1 → score = 100 (fort BUY)
# confidence = 0.5, direction = -1 → score = 25 (SELL modéré)
# confidence = 0.0                → score = 50 (neutre)

score_ajusté = 50.0 + (score - 50.0) × regime_multiplier
# Exemple : score=80, VOLATILE (×0.75) → 50 + (80-50)×0.75 = 72.5
# Exemple : score=80, TRENDING (×1.10) → 50 + (80-50)×1.10 = 83.0
```

### Rôle critique de E dans la fusion

Le Modèle E est le seul avec A à avoir un **droit de veto directionnel** : si A dit BUY et E dit SELL (ou inversement), la direction devient 0 → action = WAIT. Ce mécanisme évite les signaux contradictoires entre les stats et la structure technique.

---

## 10. Fusion des signaux — Score composite

**Fichier** : `engine/signal_fusion.py`

### Formule principale

```
Score_composite = 0.30×A + 0.20×B + 0.20×C + 0.15×D + 0.15×E
```

### Consensus directionnel

```python
dir_A = résultat du Modèle A (streak dominant)
dir_E = résultat du Modèle E (Price Action / SMC)

if dir_A != 0 and dir_E != 0:
    direction = dir_A if dir_A == dir_E else 0  # désaccord → WAIT
else:
    direction = dir_A or dir_E  # si un des deux est neutre, l'autre prime
```

**Les modèles B, C, D ne donnent pas de direction** — ils pondèrent la confiance mais ne votent pas sur BUY/SELL.

### Bonus d'alignement multi-timeframe

Calculé depuis le Modèle A (qui analyse 3 TF) + confirmation du Modèle E :

| Alignement total | Multiplicateur |
|---|---|
| ≥ 4 TF alignés | × 1.20 (bonus fort) |
| ≥ 3 TF alignés | × 1.10 |
| ≥ 2 TF alignés | × 1.05 |
| < 2 TF alignés | × 1.00 + flag `reduce_size = True` |

### Niveaux de confiance

| Score | Confiance | Comportement MM |
|---|---|---|
| ≥ 72 | HIGH | RR favorable possible |
| 56 – 71 | MEDIUM | RR standard |
| 40 – 55 | LOW | LLM consulté + taille réduite possible |
| < 40 | — | WAIT obligatoire |

### Règle absolue — MIN_SCORE_TO_TRADE = 40

Si `score < 40` **OU** `direction == 0` → `action = WAIT`. Aucune exception.

### Structure de sortie (CompositeSignal)

```python
CompositeSignal(
    symbol,          # Nom MT5 de l'actif
    action,          # 'BUY' | 'SELL' | 'WAIT'
    score,           # [0-100] — le chiffre clé
    direction,       # +1 | -1 | 0
    confidence,      # 'HIGH' | 'MEDIUM' | 'LOW'
    alignment,       # [0-4] TF alignés
    score_A,         # Score individuel Streaks
    score_B,         # Score individuel Volatilité
    score_C,         # Score individuel Événement
    score_D,         # Score individuel Monte Carlo
    score_E,         # Score individuel Legacy
    reduce_size,     # True si alignement faible → volume ×0.75
    spike_alert,     # True si spike détecté (modèle C)
    spike_alert_level,  # 'CRITIQUE' | 'HAUTE' | 'MOYENNE' | 'FAIBLE'
    details,         # Données brutes de chaque modèle
)
```

---

## 11. LLM Advisor

**Fichier** : `engine/llm_advisor.py`

### Quand est-il appelé ?

**Uniquement** si les 3 conditions sont réunies :
1. `DTE_USE_LLM = true` dans `.env`
2. Le signal concerne le symbole **actif** (pas les 7 autres surveillés)
3. **Score entre 40 et 65** (zone borderline — signal valide mais incertain)

Pour les scores > 65 ou les modes sans LLM, la décision est prise par le système seul.

### Modèles utilisés

| Priorité | Modèle | Usage |
|---|---|---|
| 1 (primaire) | Claude Haiku (`claude-haiku-4-5-20251001`) | Rapide, peu coûteux |
| 2 (fallback) | GPT-4o-mini | Si Anthropic indisponible |

### Prompt envoyé au LLM

Le prompt inclut : actif, action brute, score, direction, confiance, alignement, scores A/B/C/D, alerte spike, flag reduce_size, solde du compte.

Réponse demandée en **JSON strict** :
```json
{
  "confirmed": true,
  "adjusted_score": 58.0,
  "reason": "Streak fort Crash 500 mais volatilité en compression",
  "risk": "MEDIUM"
}
```

### Impact sur la décision

```python
if llm_advice['llm_used'] and not llm_advice['confirmed']:
    signal['action'] = 'WAIT'  # LLM a infirmé → on ne trade pas
    # Même en FULL_AUTO, ce veto est respecté
```

Si le LLM confirme mais donne un `adjusted_score` différent, le score original du composite est conservé pour le sizing (prudence).

---

## 12. Gestion des positions — Sizing, SL, TP

**Fichiers** : `engine/money_manager.py`, `engine/mt5_data_provider.py`, `main/dte_main.py`

### Étape 1 — Calcul dynamique du SL et TP

**Fichier** : `MT5DataProvider.compute_sl_tp_dynamic()`

Le SL et le TP sont calculés dynamiquement à chaque trade — ils s'adaptent à la volatilité courante mesurée sur M1.

#### Calcul du SL

```
ATR_M1 = moyenne mobile 14 périodes des ranges (high - low) sur M1
atr_pips = ATR_M1 / pip_size

sl_pips_dynamique = atr_pips × multiplicateur_actif
sl_pips_final = max(plancher_minimum, sl_pips_dynamique)
```

**Multiplicateurs par actif** :

| Actif | Mult ATR | Raison |
|---|---|---|
| Crash 500 Index | × 2.5 | Spikes brusques → risque stop-hunt |
| Crash 1000 Index | × 2.5 | Idem |
| Boom 500 Index | × 2.5 | Idem |
| Boom 1000 Index | × 2.5 | Idem |
| Volatility 100 (1s) | × 2.0 | Tick très rapide |
| Volatility 100 | × 1.8 | Mouvement régulier mais volatile |
| Range Break 100 | × 1.5 | Mouvement en range avec breaks |
| Step Index | × 1.2 | Mouvements en paliers — très réguliers |

**Planchers minimums (SL absolu)** :

| Actif | SL minimum |
|---|---|
| Volatility 100 Index | 20 pips |
| Volatility 100 (1s) Index | 25 pips |
| Crash 500 Index | 15 pips |
| Crash 1000 Index | 20 pips |
| Boom 500 Index | 15 pips |
| Boom 1000 Index | 25 pips |
| Step Index | 30 pips |
| Range Break 100 Index | 50 pips |

**Exemple concret — Crash 500** :
```
ATR M1 = 8 pips → sl_dynamique = 8 × 2.5 = 20 pips
sl_final = max(15, 20) = 20 pips (ATR domine)

ATR M1 = 4 pips → sl_dynamique = 4 × 2.5 = 10 pips
sl_final = max(15, 10) = 15 pips (plancher actif)
```

#### Calcul du TP — RR dynamique selon le score

```python
if spike_alert:    rr = 1.2   # Sortie rapide avant/après spike
elif score >= 80:  rr = 2.5   # Signal fort → laisser courir
elif score >= 65:  rr = 2.0   # Signal bon → RR généreux
else:              rr = 1.5   # Signal borderline → RR prudent

tp_pips = sl_pips × rr
```

**Tableau RR × SL = TP** (exemple Crash 500, ATR M1 = 8 pips, sl = 20 pips) :

| Situation | RR | TP |
|---|---|---|
| Spike alert (sortie rapide) | 1.2 | 24 pips |
| Score 42 (borderline) | 1.5 | 30 pips |
| Score 70 (bon signal) | 2.0 | 40 pips |
| Score 85 (signal fort) | 2.5 | 50 pips |

#### Prix SL/TP absolus

Le calcul travaille **entièrement en unités de prix brutes** (via `sym_info.point` de MT5, jamais en pips arbitraires) pour éviter toute ambiguïté de conversion :

```python
# ATR en raw price units (high - low du candle M1)
atr_raw = m1['range'].rolling(14).mean().iloc[-1]

sl_dist = max(plancher_minimum × point, atr_raw × mult)

# Respect de la distance minimale imposée par le broker
broker_min = sym_info.trade_stops_level × point
sl_dist = max(sl_dist, broker_min, spread × 2, point × 10)

tp_dist = sl_dist × rr

# Calcul des prix absolus (arrondis aux décimales du symbole)
# Pour un BUY :
sl_price = round(price_ask - sl_dist, sym_info.digits)
tp_price = round(price_ask + tp_dist, sym_info.digits)

# Pour un SELL :
sl_price = round(price_bid + sl_dist, sym_info.digits)
tp_price = round(price_bid - tp_dist, sym_info.digits)
```

Ces prix absolus sont transmis directement à `place_order()` — aucune reconversion depuis les pips.

### Étape 2b — Gestion active des positions (Trailing Stop + Breakeven)

**Fichier** : `DTEEngine._manage_open_positions()` — appelée toutes les 10 secondes.

#### Breakeven (mise à zéro du risque)

Déclenchement quand le profit de la position atteint **≥ 50% de la distance SL initiale** :

```python
# Ex : SL initial = 50 pips → déclenchement quand profit ≥ 25 pips
be_sl = entry_price + buffer (2% du SL, pour couvrir le spread)
# Pour BUY : SL déplacé juste au-dessus du prix d'entrée
# Pour SELL : SL déplacé juste en-dessous du prix d'entrée
```

→ **Résultat** : la position ne peut plus perdre. Le pire cas est un profit nul (ou légèrement positif).

#### Trailing Stop (verrouillage du profit)

Déclenchement quand le profit atteint **≥ 100% de la distance SL initiale** :

```python
# Le SL suit le cours à une distance de 50% du SL initial
# Pour BUY : new_sl = current_price - sl_dist × 0.5
# Pour SELL : new_sl = current_price + sl_dist × 0.5
```

→ **Résultat** : le SL se déplace vers le haut à mesure que le prix monte (BUY). Le profit minimum garanti augmente continuellement.

**Exemple complet — BUY Crash 500 (SL initial = 500 pips) :**

| Profit courant | Action | SL déplacé à |
|---|---|---|
| 250 pips (50%) | Breakeven | Entry + 2% buffer |
| 500 pips (100%) | Trailing activé | Current - 250 pips |
| 800 pips | Trailing mis à jour | Current - 250 pips |
| Position clôturée par SL | Profit minimum garanti | +250 pips |

### Étape 2 — Money Manager : calcul de la mise

**Fichier** : `MoneyManager.get_position_size()`

Le MoneyManager reçoit le `rr_ratio` dynamique calculé à l'étape 1, ce qui améliore la formule Kelly.

#### Stratégie FLAT

```
risk_pct = base_risk_pct (défaut : 1% du capital)
```

Simple et prévisible. Chaque trade risque le même pourcentage.

#### Stratégie KELLY (recommandée)

```
Formule Kelly complète :
  f* = (p × b - q) / b

  p = win_prob / 100  (≈ score composite / 100)
  q = 1 - p
  b = rr_ratio  (le ratio risque/récompense dynamique)

Fraction utilisée : f* / 4  (¼ Kelly — plus conservateur)
Borné entre 0.5% et 2% du capital
```

Exemple avec score = 75, RR = 2.0 :
```
p = 0.75, q = 0.25, b = 2.0
f* = (0.75×2.0 - 0.25) / 2.0 = 0.625
¼ Kelly = 0.625 / 4 = 15.6% → borné à 2% (MAX_RISK)
```

#### Stratégie MARTINGALE

```
mise = base_risk_pct × 2^niveau_martingale

Niveau 0 (gain ou start)  : 1%
Niveau 1 (1ère perte)     : 2%
Niveau 2 (2ème perte)     : 4%  → mais borné à 2% MAX_RISK
Niveau 3                  : 8%  → borné
Niveau 4                  : 16% → borné
Niveau 5 (max)            : reset au niveau 0
```

**Important** : même en Martingale, le plafond de 2% s'applique. Au-delà de 5 niveaux, reset automatique à 0.

#### Modulation par le score

```python
# Tous les modes appliquent ce facteur :
score_factor = 0.80 + (score - 40) / (100 - 40) × 0.20
# Score 40 → ×0.80 (mise réduite de 20%)
# Score 70 → ×0.90
# Score 100 → ×1.00 (mise pleine)

risk_pct_final = min(risk_pct × score_factor, 2%)
```

#### Vérifications avant de valider

```python
# 1. Session stoppée ? → STOP_SESSION
# 2. Capital < 5 USD ? → STOP_SESSION
# 3. Drawdown session ≥ 10% ? → STOP_SESSION (bascule SIGNAL_ONLY)
# 4. Score < 40 ? → WAIT
# Sinon → TRADE avec le montant calculé
```

### Étape 3 — Calcul du volume en lots

**Fichier** : `MT5DataProvider.calculate_volume()`

```
pip_value_per_lot = (pip_size / tick_size) × tick_value

volume_lots = risk_amount / (sl_pips × pip_value_per_lot)

Contraintes MT5 :
  volume = max(volume_min, min(volume_max, volume))
  volume = arrondi au volume_step
```

Le `tick_value` et le `tick_size` sont lus directement depuis MT5 (`mt5.symbol_info()`) — aucune valeur codée en dur pour le calcul du volume.

### Étape 4 — Réduction de volume si alignement faible

```python
if reduce_size:  # alignment < 3 TF alignés
    volume = round(volume × 0.75, 8)
    # Taille réduite de 25% car signal moins fiable
```

**Important** : au lieu d'élargir le SL (ancienne logique erronée), on réduit la taille. Le SL reste basé sur l'ATR et le contexte du marché.

### Étape 5 — Envoi de l'ordre à MT5

```python
# Vérification préalable : déjà une position ouverte sur ce symbole ?
if existing_positions:
    skip  # Une position à la fois par symbole

# Ordre envoyé :
MT5DataProvider.place_order(
    symbol, direction, volume,
    sl_pips, tp_pips,
    comment = f'DTE_{symbol[:8]}_S{score:.0f}'
)
```

L'ordre est estampillé avec `MAGIC_NUMBER = 20260617` pour identifier toutes les positions du système DTE dans MT5.

### Log complet d'un trade

```
TRADE BUY Crash 500 Index | Vol:0.02 | Prix:3058.0910 | SL:3043.7660 TP:3083.6160 RR:2.5 ATR:5.9p | Score:82
```

Note : SL et TP sont maintenant en **prix absolus** (non en pips), ce qui évite toute erreur de conversion et garantit l'exactitude même si `sym_info.point` diffère de la valeur attendue.

### Stop de session automatique

Si la perte cumulée depuis le début de la session atteint **-10% du capital de départ** :
1. `session_stopped = True` dans MoneyManager
2. Mode bascule automatiquement de FULL_AUTO → SIGNAL_ONLY
3. Alerte CRITIQUE envoyée à l'API et à l'extension Chrome
4. **Le bot ne reprend jamais en auto seul** — redémarrage manuel requis

---

## 13. MT5 Data Provider — Exécution des ordres

**Fichier** : `engine/mt5_data_provider.py`

### Connexion

```python
mt5.initialize()
mt5.login(login=201797413, password='zoldycK*2002', server='Deriv-Demo')
```

La connexion est vérifiée avant chaque opération (`ensure_connected()`). En cas de perte, reconnexion automatique.

### Tailles de pip par actif

| Actif | Pip size |
|---|---|
| Volatility 100 Index | 0.01 |
| Volatility 100 (1s) Index | 0.01 |
| Crash 500 Index | 0.001 |
| Crash 1000 Index | 0.001 |
| Boom 500 Index | 0.001 |
| Boom 1000 Index | 0.001 |
| Step Index | 0.1 |
| Range Break 100 Index | 0.1 |

### Paramètres de l'ordre MT5

```python
{
    'action':       TRADE_ACTION_DEAL,      # Exécution immédiate
    'symbol':       mt5_sym,
    'volume':       volume,                 # En lots
    'type':         ORDER_TYPE_BUY/SELL,
    'price':        tick.ask / tick.bid,    # Prix courant
    'sl':           sl_price,              # Prix absolu stop-loss (depuis compute_sl_tp_dynamic)
    'tp':           tp_price,              # Prix absolu take-profit
    'deviation':    50,                    # Slippage max autorisé (50 points)
    'magic':        20260617,              # Identifiant DTE
    'comment':      'DTE_Crash50_S82',
    'type_time':    ORDER_TIME_GTC,        # Ordre valide jusqu'à annulation
    'type_filling': ORDER_FILLING_FOK,     # Fill or Kill (seul mode supporté par Deriv Demo synthetics)
}
```

> **Note** : `ORDER_FILLING_IOC` (Immediate or Cancel) n'est **pas supporté** par Deriv Demo sur les indices synthétiques. `ORDER_FILLING_FOK` est le mode correct.

### Modification de position — Trailing Stop et Breakeven

```python
# Via TRADE_ACTION_SLTP (aucune fermeture/réouverture)
mt5.order_send({
    'action':   TRADE_ACTION_SLTP,
    'symbol':   pos.symbol,
    'position': ticket,
    'sl':       new_sl,   # nouveau prix stop-loss
    'tp':       pos.tp,   # take-profit inchangé
})
```

### Gestion des positions ouvertes

`get_open_positions()` filtre par `MAGIC_NUMBER = 20260617` — retourne uniquement les positions ouvertes par ce système, pas les trades manuels.

`close_all_positions()` : clôture d'urgence — ferme toutes les positions DTE simultanément (utilisé par l'endpoint `/api/emergency_stop`).

---

## 14. API FastAPI

**Fichier** : `api/main.py`  
**Port** : 8000  
**URL base** : `http://localhost:8000`

### Endpoints disponibles

| Route | Méthode | Description |
|---|---|---|
| `/` | GET | Status health check |
| `/api/status` | GET | État du moteur (running, mode, uptime) |
| `/api/signal` | GET | Signal du symbole actif courant |
| `/api/account` | GET | Informations compte MT5 (solde, equity, margin) |
| `/api/positions` | GET | Liste des positions ouvertes (DTE uniquement) |
| `/api/stats` | GET | Statistiques de session (trades, win rate, PnL) |
| `/api/alerts` | GET | Dernières 200 alertes système |
| `/api/full_state` | GET | Tout l'état en un seul appel (extension Chrome) |
| `/api/mode` | POST | Changer le mode : `{"mode":"FULL_AUTO"}` |
| `/api/symbol` | POST | Changer le symbole actif : `{"symbol":"Boom 500 Index"}` |
| `/api/emergency_stop` | POST | Arrêt d'urgence + fermeture de toutes les positions |
| `/ws` | WebSocket | Push temps réel à chaque cycle (toutes les ~2s) |

### Changement de mode à chaud

Sans redémarrer le bot :

```bash
# Passer en FULL_AUTO
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"FULL_AUTO"}'

# Revenir en SIGNAL_ONLY
curl -X POST http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode":"SIGNAL_ONLY"}'

# Arrêt d'urgence
curl -X POST http://localhost:8000/api/emergency_stop
```

### Structure de l'état complet (`/api/full_state`)

```json
{
  "running": true,
  "mode": "SIGNAL_ONLY",
  "active_symbol": "Crash 500 Index",
  "signals": {
    "Crash 500 Index": {
      "action": "BUY",
      "score": 78.5,
      "direction": 1,
      "confidence": "HIGH",
      "alignment": 3,
      "scores": {"A": 82.1, "B": 75.0, "C": 67.3, "D": 61.0, "E": 72.0},
      "reduce_size": false,
      "spike_alert": true,
      "spike_alert_level": "HAUTE"
    }
  },
  "account": {"balance": 10000, "equity": 10050, "currency": "USD"},
  "positions": [],
  "session_stats": {"trades": 3, "wins": 2, "losses": 1, "pnl": 45.20},
  "last_update": "2026-06-17T14:30:15"
}
```

---

## 15. Extension Chrome

**Dossier** : `chrome_extension/`  
**Version manifest** : MV3  
**Permissions** : `*.deriv.com/*`, `localhost:8000/*`

### Installation

1. Chrome → `chrome://extensions/`
2. Mode développeur → ON
3. "Charger l'extension non empaquetée"
4. Sélectionner `c:\thMonster_v2_Top\chrome_extension\`

### Composants

| Fichier | Rôle |
|---|---|
| `manifest.json` | Configuration MV3, permissions, scripts |
| `content_script.js` | Panneau overlay injecté sur deriv.com |
| `overlay.css` | Styles du panneau (dark theme, cyan `#00D4FF`) |
| `popup.html` | Interface du bouton d'extension |
| `popup.js` | Logique du popup |
| `background.js` | Notifications Chrome + keepalive |

### Panneau overlay

- Flottant, déplaçable par drag & drop
- Masquable/affichable (bouton toggle)
- Affiche en temps réel :
  - Score composite / 100
  - Action (BUY vert / SELL rouge / WAIT gris)
  - 5 scores modèles A/B/C/D/E
  - Barres visuelles A/B/C
  - Streaks M1/M5/M15 avec couleurs directionnelles
  - Alerte spike (clignotante si CRITIQUE)
  - Mode actif + heure de dernière mise à jour

### Connexion au backend

**Double stratégie de connexion** :
1. **WebSocket** (`ws://localhost:8000/ws`) — push temps réel toutes les ~2s
2. **Polling REST** (`/api/full_state`) toutes les 1.5s — fallback si WebSocket déconnecté

Reconnexion WebSocket automatique après 5 secondes de déconnexion.

### Notifications

Si `spike_alert_level = 'CRITIQUE'` → notification système Chrome avec nom de l'actif et direction.

### Boutons du popup

- **SIGNAL_ONLY** / **SEMI_AUTO** / **FULL_AUTO** — change le mode via `POST /api/mode`
- Sélecteur des 8 actifs — change le symbole actif via `POST /api/symbol`

---

## 16. Modes de fonctionnement

### Architecture des deux fenêtres de console

Lors du démarrage, le bot **ouvre automatiquement une seconde fenêtre PowerShell** qui affiche les logs détaillés en temps réel (tail du fichier `.log`).

**Fenêtre principale** : affiche seulement :
- Résumé des positions + P&L toutes les **5 minutes**
- Chaque TRADE exécuté (en vert) au moment où il se produit
- Les erreurs critiques

**Fenêtre secondaire "DTE — Logs détaillés"** : affiche tout (cycle par cycle, signal par symbole, ATR, trailing/BE).

### SIGNAL_ONLY

Calcule et affiche tous les signaux. Aucun ordre envoyé. Le MoneyManager calcule les tailles théoriques sans jamais les exécuter.

**Usage** : validation du système, audit des signaux, monitoring sans risque.

### SEMI_AUTO

Même comportement que SIGNAL_ONLY mais affiche une alerte console explicite quand un signal valide est détecté sur le symbole actif. L'exécution reste entièrement manuelle (dans MT5 ou via le popup).

**Usage** : phase de confiance — observer les signaux et prendre manuellement ceux qui paraissent bons.

### FULL_AUTO

Exécute automatiquement les trades selon le pipeline complet (SL/TP dynamiques, sizing Kelly, règles absolues). Les modifications de mode sont possibles à chaud via l'API ou le popup. La gestion active des positions (trailing stop, breakeven) est activée en FULL_AUTO.

**Usage** : uniquement après validation approfondie en SIGNAL_ONLY.

### Passage entre les modes

Les modes peuvent être changés sans redémarrer le bot :
- Via l'API REST : `POST /api/mode`
- Via le popup de l'extension Chrome
- Via la console : le moteur relit `_state['mode']` à chaque cycle

---

## 17. Règles absolues du système

Ces règles ne peuvent être ni contournées ni désactivées dans le code.

| Règle | Valeur | Comportement |
|---|---|---|
| Score minimum pour trader | 40 / 100 | En dessous → WAIT automatique |
| Risque maximum par trade | 2% du capital | Plafond absolu sur toutes les stratégies |
| Stop de session | -10% de drawdown | Bascule FULL_AUTO → SIGNAL_ONLY |
| Martingale niveaux max | 5 | Au niveau 6 → reset au niveau 0 |
| Positions simultanées par symbole | 1 | Vérifié avant chaque ordre |
| Magic number | 20260617 | Identifie toutes les positions DTE |

---

## 18. Structure des fichiers

```
thMonster_v2_Top/
│
├── engine/                     ← Moteur de calcul DTE
│   ├── __init__.py
│   ├── streak_analyser.py      ← Modèle A — Streaks empiriques
│   ├── volatility_detector.py  ← Modèle B — Phases ATR
│   ├── event_detector.py       ← Modèle C — Spikes Crash/Boom
│   ├── monte_carlo.py          ← Modèle D — Simulations
│   ├── legacy_adapter.py       ← Modèle E — Price Action SMC
│   ├── signal_fusion.py        ← Fusion 5 modèles → score composite
│   ├── money_manager.py        ← Kelly / Martingale / Flat
│   ├── llm_advisor.py          ← Claude Haiku / GPT-4o-mini
│   └── mt5_data_provider.py    ← Données MT5 + ordres + SL/TP dynamiques
│
├── main/
│   └── dte_main.py             ← Point d'entrée principal + boucle
│
├── api/
│   └── main.py                 ← FastAPI REST + WebSocket
│
├── chrome_extension/           ← Extension Chrome MV3
│   ├── manifest.json
│   ├── content_script.js
│   ├── overlay.css
│   ├── popup.html
│   ├── popup.js
│   └── background.js
│
├── strategies/                 ← Stratégies legacy (utilisées par Modèle E)
│   ├── crash_boom_strategy.py
│   ├── top_volatility_strategy.py
│   └── volatility_strategy.py
│
├── core/                       ← Composants legacy (utilisés par Modèle E)
│   ├── price_action.py
│   ├── market_regime_detector.py
│   └── ...
│
├── .env                        ← Credentials (exclu du git)
├── .gitignore
├── requirements.txt
├── LANCEMENT.md                ← Guide de démarrage rapide
└── DTE_AUDIT_COMPLET.md        ← Ce document
```

---

## 19. Guide de lancement

### Prérequis

- Python 3.12 : `C:\Users\Emma\AppData\Local\Programs\Python\Python312\python.exe`
- MetaTrader 5 installé avec compte demo connecté
- Compte demo : Login `201797413`, Serveur `Deriv-Demo`

### Création et activation du venv

```powershell
cd c:\thMonster_v2_Top
c:\Users\Emma\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
.venv\Scripts\Activate.ps1
```

### Packages installés dans le venv

```
pandas 3.0.3       numpy 2.4.6        scipy 1.17.1
MetaTrader5 5.0.5735
fastapi 0.137.1    uvicorn 0.13.4     pydantic 2.13.4
websockets 16.0    python-dotenv 1.2.2
anthropic 0.109.2  openai 2.42.0
ta 0.11.0          colorama 0.4.6
```

### Vérification MT5

1. Ouvrir MetaTrader 5
2. Se connecter au compte demo (Login : 201797413, Deriv-Demo)
3. Vérifier que les 8 actifs Deriv sont visibles dans Market Watch

### Commandes de lancement

```powershell
# Mode lecture — recommandé pour commencer
python -m main.dte_main --all-symbols --strategy FLAT --mode SIGNAL_ONLY

# Mode semi-auto
python -m main.dte_main --all-symbols --strategy FLAT --mode SEMI_AUTO

# Mode full auto avec Kelly
python -m main.dte_main --all-symbols --strategy KELLY --mode FULL_AUTO

# Sans LLM (plus rapide)
python -m main.dte_main --all-symbols --strategy FLAT --mode SIGNAL_ONLY --no-llm

# Symbole unique
python -m main.dte_main --symbol "Crash 500 Index" --strategy FLAT --mode SIGNAL_ONLY
```

### Sortie console attendue

```
════════════════════════════════════════════════════════════
DTE Engine démarrage…
  Symboles : ['Volatility 100 Index', 'Crash 500 Index', ...]
  Stratégie MM : FLAT
  Mode : SIGNAL_ONLY
════════════════════════════════════════════════════════════
Compte MT5 | Login: 201797413 | Solde: 10000.00 USD
API FastAPI démarrée sur http://localhost:8000

▲ Crash 500 Index              | Score:  82.0 | BUY   | A: 88 B: 75 C: 68 D: 63 E: 72 | Align:3
— Volatility 100 Index         | Score:  51.2 | WAIT  | A: 53 B: 50 C: 50 D: 48 E: 52 | Align:1
▼ Boom 500 Index               | Score:  76.4 | SELL  | A: 92 B: 75 C: 71 D: 55 E: 69 | Align:3
```

### URLs actives

| Service | URL |
|---|---|
| API racine | http://localhost:8000 |
| Status | http://localhost:8000/api/status |
| Signal | http://localhost:8000/api/signal |
| État complet | http://localhost:8000/api/full_state |
| WebSocket | ws://localhost:8000/ws |

---

*Document généré le 2026-06-17 — DTE v1.0 — thMonster_v2_Top*
