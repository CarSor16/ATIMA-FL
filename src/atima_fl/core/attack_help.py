"""Plain-language help for the built-in attack catalog.

Descriptions concern the implemented laboratory mechanisms. Parameter magnitude
is not a guarantee of attack efficacy, stealth or network feasibility.
"""

ATTACK_HELP = {
    "none": {
        "en": ("No malicious transformation is applied. Use this run as the reference for a matched attack experiment.",
               "There is no attack intensity."),
        "it": ("Nessuna trasformazione malevola. Usa questa run come riferimento per un attacco con configurazione abbinata.",
               "Non esiste un parametro di intensità."),
    },
    "label_flip": {
        "en": ("A compromised client changes selected labels from one source class to a destination class before local training. The features stay unchanged.",
               "poison_rate controls the fraction of eligible source examples relabeled. The source and destination identify the classes, not the intensity. No source examples means no relabeling."),
        "it": ("Prima del training locale, il client compromesso cambia le etichette di alcuni esempi dalla classe sorgente a quella di destinazione. Le feature restano invariate.",
               "poison_rate indica la quota di esempi della classe sorgente rietichettati. source_class e destination_class scelgono le classi. Se mancano esempi sorgente, non avviene alcuna modifica."),
    },
    "random_labels": {
        "en": ("The client replaces labels on selected training examples with random labels. This is untargeted data poisoning.",
               "poison_rate changes how many examples are selected. It does not prescribe which class errors will appear."),
        "it": ("Il client sostituisce le etichette di alcuni esempi con etichette casuali. Non sceglie una coppia di classi da colpire.",
               "poison_rate stabilisce quanti esempi vengono selezionati; non determina quali classi saranno confuse."),
    },
    "feature_noise": {
        "en": ("The client adds Gaussian noise to selected feature coordinates, clips the resulting values and keeps the original labels.",
               "poison_rate controls how many rows are selected; sigma controls the numerical noise scale. Coordinate selection and clipping also affect the perturbation. Valid feature vectors are not necessarily realizable traffic."),
        "it": ("Il client aggiunge rumore gaussiano alle feature selezionate, limita i valori all'intervallo configurato e conserva le etichette originali.",
               "poison_rate regola la quota di righe coinvolte e sigma l'ampiezza del rumore numerico. Coordinate e limiti di clipping influiscono sulla perturbazione. La fattibilità su pacchetti reali non è dimostrata."),
    },
    "class_withholding": {
        "en": ("The compromised client removes a fraction of the selected class from its local training set without changing the remaining labels.",
               "remove_fraction changes the proportion withheld. The actual number removed depends on local target-class support; absent or very small classes can produce no change."),
        "it": ("Il client compromesso esclude dal training locale una parte degli esempi della classe scelta, senza cambiare le etichette rimanenti.",
               "remove_fraction indica la frazione esclusa. Il numero effettivo dipende dal supporto locale della classe; con pochi o nessun esempio la modifica può essere nulla."),
    },
    "update_scaling": {
        "en": ("The client multiplies its local model delta relative to the received global model. The direction is unchanged.",
               "factor controls the delta magnitude; 1 leaves it unchanged. A larger factor changes the submitted update, but does not guarantee a larger classification error."),
        "it": ("Il client moltiplica la differenza fra modello locale e modello globale ricevuto, mantenendo la direzione dell'aggiornamento.",
               "factor regola l'ampiezza del delta; con 1 non cambia. Un fattore maggiore modifica il contributo inviato, ma non garantisce un peggioramento maggiore."),
    },
    "sign_flip": {
        "en": ("The submitted delta points in the opposite direction to the client's local training update.",
               "strength sets the magnitude of the reversed delta. It does not change the number of malicious clients."),
        "it": ("Il delta inviato ha direzione opposta rispetto all'aggiornamento ottenuto dal training locale.",
               "strength regola l'ampiezza del delta invertito. Il numero di client malevoli è una variabile distinta."),
    },
    "gaussian_noise": {
        "en": ("The attack adds a random Gaussian direction to the local model delta, with a budget relative to the delta's L2 norm.",
               "relative_l2 sets the norm of the added noise relative to the original delta. Zero adds no noise; this parameter does not perturb raw input data."),
        "it": ("L'attacco aggiunge al delta locale una direzione gaussiana casuale, con un budget relativo alla sua norma L2.",
               "relative_l2 imposta la norma del rumore aggiunto rispetto al delta originale. Con zero non si aggiunge rumore; le feature dei dati non vengono modificate."),
    },
    "alie": {
        "en": ("ALIE uses the mean and coordinate-wise variation of available local models to construct a statistical perturbation.",
               "alie_z controls the displacement in standard-deviation units; -1 requests the automatic bound, which may be zero or invalid. Local knowledge requires colluding clients; oracle knowledge is a separate assumption."),
        "it": ("ALIE costruisce una perturbazione statistica usando la media e la variabilità per coordinata dei modelli disponibili.",
               "alie_z regola lo spostamento in unità di deviazione standard; -1 richiede il limite automatico, che può risultare nullo o non valido. La modalità locale richiede collusione; oracle assume una visibilità diversa."),
    },
    "ipm": {
        "en": ("IPM submits a delta opposed to the mean benign update in the oracle simulation.",
               "ipm_epsilon scales the opposite direction. The current implementation requires oracle access, so its results do not establish local-only attack feasibility."),
        "it": ("IPM invia un delta opposto all'aggiornamento benigno medio osservato nella simulazione oracle.",
               "ipm_epsilon regola l'ampiezza in direzione opposta. L'implementazione richiede conoscenza oracle: non dimostra la fattibilità con sola conoscenza locale."),
    },
    "fang": {
        "en": ("Fang constructs model submissions for a specified robust aggregation rule using oracle information. The Krum and trimmed-mean variants differ.",
               "fang_b controls the coordinate range for the trimmed-mean variant. The Krum variant searches its own magnitude and uses byzantine_bound as a feasibility constraint, not an intensity knob."),
        "it": ("Fang costruisce contributi malevoli in funzione della regola di aggregazione, usando informazioni oracle. Le varianti Krum e trimmed mean hanno meccanismi distinti.",
               "fang_b regola l'intervallo delle coordinate nella variante trimmed mean. Krum cerca internamente l'ampiezza; byzantine_bound è un vincolo di fattibilità, non un livello di intensità."),
    },
    "min_max": {
        "en": ("Min-Max constructs a Byzantine model under a maximum-distance constraint derived from benign models.",
               "The implementation determines the candidate internally from oracle data. It has no independent user-set strength parameter."),
        "it": ("Min-Max costruisce un modello Byzantine con un vincolo sulla distanza massima ricavato dai modelli benigni.",
               "Il candidato viene determinato internamente usando dati oracle. Non è previsto un parametro di intensità indipendente."),
    },
    "min_sum": {
        "en": ("Min-Sum constructs a Byzantine model under a summed squared-distance constraint derived from benign models.",
               "The candidate is determined internally under the oracle constraint. No independent strength setting is exposed."),
        "it": ("Min-Sum costruisce un modello Byzantine con un vincolo sulla somma delle distanze quadratiche dai modelli benigni.",
               "Il candidato viene determinato internamente entro il vincolo oracle. Non è disponibile un controllo di intensità indipendente."),
    },
    "random_byzantine": {
        "en": ("A seeded random direction replaces the local delta. This is a generic experimental control, not a paper-specific optimized attack.",
               "relative_l2 specifies the submitted norm relative to the original delta. A zero reference delta can prevent a meaningful replacement."),
        "it": ("Una direzione casuale riproducibile sostituisce il delta locale. È un controllo sperimentale generico, non un attacco ottimizzato di uno specifico paper.",
               "relative_l2 indica la norma del delta inviato rispetto a quello originale. Un delta di riferimento nullo può rendere impossibile una sostituzione significativa."),
    },
    "local_class_gradient": {
        "en": ("LocalClassGradient adds a bounded gradient-ascent perturbation using examples of the target class in the compromised client's own shard. It supports the standard and HyperFL++ paths.",
               "relative_budget sets the perturbation budget relative to the local update. max_examples caps the examples used for the gradient; target_class selects the class. Missing target support or a zero gradient can prevent application. Recall loss is not guaranteed."),
        "it": ("LocalClassGradient aggiunge una perturbazione di gradient ascent calcolata sugli esempi della classe bersaglio nello shard del client compromesso. Sono previsti i percorsi standard e HyperFL++.",
               "relative_budget regola il budget rispetto al delta locale. max_examples limita gli esempi usati per calcolare il gradiente; target_class sceglie la classe. Senza esempi bersaglio o con gradiente nullo l'attacco può non essere applicato. Il calo del recall va misurato."),
    },
    "clean_label_trigger": {
        "en": ("The client modifies selected examples of the target class with a numerical trigger but keeps their labels.",
               "poison_rate controls the selected fraction; trigger_indices and trigger_values define the transformation, not a universal intensity scale. Physical traffic validity requires a separate check."),
        "it": ("Il client applica un trigger numerico a una parte degli esempi della classe bersaglio, lasciandone invariate le etichette.",
               "poison_rate regola la quota selezionata; trigger_indices e trigger_values definiscono la trasformazione, non una scala universale di forza. La plausibilità del traffico richiede una verifica separata."),
    },
    "model_replacement": {
        "en": ("ModelReplacement adds triggered training examples with the target label and scales the submitted local update using the public sample mass. The global model need not be exactly replaced.",
               "poison_rate controls the fraction of eligible non-target examples used for the extra training examples. The trigger and target define the test; the replacement scale is calculated internally. Zero poison_rate does not disable update scaling."),
        "it": ("ModelReplacement aggiunge esempi di training con trigger ed etichetta bersaglio, poi scala il delta inviato in base alla massa campionaria pubblica. Il modello globale non viene necessariamente sostituito esattamente.",
               "poison_rate regola la quota di esempi non bersaglio da cui derivano quelli aggiuntivi. Trigger e destinazione definiscono il test; il fattore di replacement è calcolato internamente. Con poison_rate zero, lo scaling resta attivo."),
    },
    "sample_weight_hijack": {
        "en": ("The client reports an inflated sample count, changing its influence when the aggregator trusts that count. Its local training data and model remain unchanged.",
               "count_multiplier sets the reported-count multiplier. Its effect depends on the aggregator's treatment of counts and other clients' sample mass."),
        "it": ("Il client dichiara un conteggio campionario superiore a quello effettivo, alterando il proprio peso se l'aggregatore si fida di tale valore. Dati e modello locale restano invariati.",
               "count_multiplier moltiplica il conteggio dichiarato. L'effetto dipende dalla regola con cui l'aggregatore usa i conteggi e dalla massa degli altri client."),
    },
    "sybil_collusion": {
        "en": ("Multiple compromised logical clients submit the same leader's model. This simulates collusion among existing clients, not creation of fake authenticated identities.",
               "There is no independent strength parameter. The configured participants and their sample masses determine how much of the aggregation is affected."),
        "it": ("Più client logici compromessi inviano il modello del medesimo leader. Si simula la collusione fra identità esistenti, senza creare identità autenticate false.",
               "Non esiste un parametro di intensità indipendente. I partecipanti configurati e i loro pesi campionari determinano la porzione di aggregazione coinvolta."),
    },
    "stale_replay": {
        "en": ("The client submits a stored local model from an earlier round instead of its current model.",
               "lag_rounds selects how old the snapshot is; the required prior snapshot must exist. This simulates replayed contributions, not a measured network delay."),
        "it": ("Il client invia un modello locale salvato in un round precedente al posto di quello corrente.",
               "lag_rounds indica quanti round indietro risale lo snapshot, che deve esistere. Il meccanismo simula un contributo obsoleto, non un ritardo di rete misurato."),
    },
    "free_rider": {
        "en": ("The current plugin submits the received global trainable parameters, giving a zero submitted delta even after local training.",
               "There is no strength parameter. This is a zero-contribution control; the plugin alone does not demonstrate that local computation was skipped."),
        "it": ("Il plugin attuale invia i parametri addestrabili del modello globale ricevuto, producendo un delta nullo anche dopo il training locale.",
               "Non esiste un parametro di intensità. È un controllo a contributo nullo; il solo plugin non dimostra che il training locale sia stato evitato."),
    },
}


def attack_help(attack_id):
    """Expose optional localized help without changing a component's execution."""
    return {
        language: {"mechanism": values[0], "intensity": values[1]}
        for language, values in ATTACK_HELP.get(attack_id, {}).items()
    }
