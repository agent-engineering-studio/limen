# Training LLM per Limen — guida passo-passo

> Come addestrare (fine-tuning LoRA) un piccolo modello linguistico sul
> "dialetto" dei briefing Limen, usando **LLaMA-Factory** già installato in
> `~/Git/LlamaFactory`. Scritta per chi non ha mai fatto un training.

## Prima di iniziare: serve davvero?

**Probabilmente non ancora.** L'eval di fedeltà (2026-07) ha mostrato che
qwen3.6 **non inventa numeri** (16/16 briefing fedeli) — i difetti trovati si
sono corretti ritoccando il prompt. Il fine-tuning serve solo se, in futuro,
l'eval mostrasse errori sistematici che né prompt migliori né un modello base
diverso risolvono. Questa cartella tiene pronto tutto per quel giorno.

**Regola d'oro sul dataset**: 20 esempi (quelli attuali) bastano solo per una
prova tecnica. Per un training che migliori davvero il modello servono
**300–1000 coppie validate da una persona esperta** — vedi "Come far crescere
il dataset" in fondo.

## Cosa c'è in questa cartella

| File | Cosa contiene |
|---|---|
| `datasets/briefing_sft.json` | Coppie *(valutazione → briefing)* reali di produzione, formato **Alpaca** (`instruction` / `input` / `output`). |
| `datasets/dataset_info.snippet.json` | La voce da incollare nel registro dataset di LLaMA-Factory. |

Per rigenerare/aggiornare il dataset dai briefing più recenti nel database:

```bash
cd ~/Git/limen
uv run python scripts/export_llm_dataset.py
```

## Il training, passo per passo

Tutti i comandi si lanciano da `~/Git/LlamaFactory`. I dettagli completi
(hardware, vincoli Apple Silicon, troubleshooting) sono nel suo
`TRAINING.md` — questa è la versione minima che funziona.

### Passo 1 — Copia e registra il dataset

```bash
cd ~/Git/LlamaFactory
cp ~/Git/limen/llm-training/datasets/briefing_sft.json data/
```

Apri `data/dataset_info.json` e aggiungi questa voce (è la stessa che trovi
in `datasets/dataset_info.snippet.json`):

```json
"limen_briefing": { "file_name": "briefing_sft.json" }
```

### Passo 2 — Prepara la configurazione

Apri `configs-local/qwen3_4b_lora_sft_mac.yaml` e cambia tre righe:

```yaml
dataset: limen_briefing          # al posto dei dataset segnaposto
cutoff_len: 2048                 # gli input Limen ci stanno comodi
output_dir: saves/limen-briefing/lora/sft
```

Se il dataset è ancora piccolo (≤100 esempi) rimuovi o commenta
`max_samples` — deve usarli tutti.

### Passo 3 — Lancia il training

```bash
nohup ./start-lmf.sh train configs-local/qwen3_4b_lora_sft_mac.yaml \
  > training.log 2>&1 &
echo $! > training.pid
```

⚠️ Usa **sempre** `./start-lmf.sh`, mai `llamafactory-cli` direttamente
(lo script imposta le variabili giuste per la GPU del Mac). Al primo avvio
scarica il modello base (~8 GB): i primi minuti mostrano solo il download.

### Passo 4 — Controlla che stia imparando

```bash
tail -f training.log
```

Cerca le righe con `loss`: deve **scendere chiaramente** nelle prime
centinaia di step e poi appiattirsi. Se resta piatta da subito → dati o
learning rate da rivedere. Se risale → troppe epoche. A fine run trovi il
grafico `training_loss.png` dentro `output_dir`.

### Passo 5 — Prova il modello addestrato

```bash
./start-lmf.sh chat --model_name_or_path Qwen/Qwen3-4B-Instruct-2507 \
  --adapter_name_or_path saves/limen-briefing/lora/sft \
  --template qwen3_nothink
```

Incollagli l'`input` JSON di un esempio del dataset e confronta il briefing
con quello del modello base (stesso comando senza `--adapter_name_or_path`).
**Il giudice vero è l'eval di Limen**: i numeri citati devono coincidere con
l'assessment (`limen.agents.chat_agents.briefing_eval`).

### Passo 6 — Esporta e collega a Limen

Crea `configs-local/export.yaml`:

```yaml
model_name_or_path: Qwen/Qwen3-4B-Instruct-2507
adapter_name_or_path: saves/limen-briefing/lora/sft
template: qwen3_nothink
export_dir: output/limen-briefing-merged
export_size: 5
export_legacy_format: false
```

Poi:

```bash
./start-lmf.sh export configs-local/export.yaml
```

Il modello fuso in `output/limen-briefing-merged` si converte in GGUF e si
importa in Ollama (`ollama create limen-briefing -f Modelfile`). A quel punto
Limen lo usa **senza toccare codice**:

```bash
LLM__OLLAMA_MODEL=limen-briefing uv run limen serve
```

## Come far crescere il dataset (la parte che conta)

1. Il sistema produce briefing a ogni ciclo con escalation: rigenera il
   dataset periodicamente con `scripts/export_llm_dataset.py`.
2. **Una persona esperta corregge gli output** (stile, precisione, lessico
   ISPRA): la coppia corretta vale oro, quella grezza vale poco.
3. Gli esempi che falliscono l'eval di fedeltà vanno **corretti o esclusi**,
   mai usati così come sono.
4. Obiettivo: 300+ coppie validate prima del primo training "serio".

## Problemi comuni

| Sintomo | Rimedio |
|---|---|
| Processo ucciso / Mac che rallenta | Riduci `cutoff_len` a 1024; verifica `per_device_train_batch_size: 1`. |
| Troppo lento | Riduci `num_train_epochs`; per il run completo valuta una GPU cloud con la stessa YAML. |
| Loss `nan` | Abbassa `learning_rate` (es. `5.0e-5`); controlla che non ci siano esempi vuoti. |

Riferimenti: `~/Git/LlamaFactory/TRAINING.md` (guida completa), WebUI con
`./start-lmf.sh webui`, skill guidata `/llamafactory-sft`.
