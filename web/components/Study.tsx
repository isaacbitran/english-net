import type { Network } from "@/lib/types";
import { BENCH } from "@/lib/results";
import Scorer from "./Scorer";
import Compare from "./Compare";
import Nav from "./Nav";
import { PatchDemo, Versus } from "./Patch";
import { S } from "@/lib/patch";
import { Details, Figure, Keys } from "./ui";

/* The study page. Every number is from results/tables.md, results/patch.json, results/finetune.json
   (through web/data/replay.json) or the README; lib/results.ts says which table each comes from. */

const PARTS = [
  { id: "what", short: "What it is", q: "Can a neural network be made of English sentences?", d: "Yes. Each neuron is a yes/no question, and each has one readable weight." },
  { id: "versus", short: "Versus one question", q: "Is it better than asking one good question?", d: "Not on new data: it ties. It wins only on the sources it was trained on." },
  { id: "fix", short: "One-sentence fix", q: "Can you fix it by writing one sentence?", d: "Yes. One sentence took a missed attack family from 40.8% to 70.4% caught." },
];

export default function Study({ net, patched }: { net: Network; patched: Network }) {
  const nActive = net.neurons.filter((n) => n.status === "active").length;
  const fam = S.family, rest = S.everything_else, ft = S.finetune;
  return (
    <>
      <Nav parts={PARTS} />
      <main>
        <div className="mast">
          <div className="kicker">An interactive study</div>
          <h1>English Net</h1>
          <p className="abstract">
            A prompt-injection detector whose neurons are English yes/no questions. It ranks attacks as well as one good question does, every
            verdict names the sentences behind it, and a blind spot was fixed by writing one more sentence.
          </p>
          <div className="byline">
            <span className="au">Isaac Bitran</span><span className="sep">·</span>Brown University<span className="sep">·</span>October 2026
          </div>
          <ol className="contents">
            {PARTS.map((p, i) => (
              <li key={p.id}>
                <a href={`#${p.id}`}><span className="n">{i + 1}</span><span className="t">{p.q}</span><span className="d">{p.d}</span></a>
              </li>
            ))}
          </ol>
        </div>

        {/* ============ PART 1 ============ */}
        <section className="part" id="what">
          <div className="head">
            <div className="kicker">Part 1 · What it is</div>
            <h2>{PARTS[0].q}</h2>
            <p className="answer">
              Yes. English Net has {nActive} neurons, each one an English yes/no question, and one readable weight per question turns the
              answers into a verdict.
            </p>
            <p className="lede">
              Jev, TypeSafe AI&apos;s judgment model, answers every question about a text in one call and returns the probability of yes. The
              output layer multiplies each answer by its weight, adds them up, and calls the text an attack when the total passes a threshold. So
              every verdict can be traced to the sentences that caused it.
            </p>
          </div>
          <Figure
            n={1}
            title="Score a prompt and read every neuron"
            caption={
              <>
                Rows are sorted by how hard each question pushed. <b>Push</b> is weight times answer: positive pushes toward attack, negative toward
                benign. The preset texts use real Jev answers saved from earlier calls; other texts need a TypeSafe key.
              </>
            }
          >
            <Scorer net={net} patched={patched} />
          </Figure>
          <Keys
            items={[
              { v: String(nActive), l: "neurons, each an English question", s: "4 of them written by the training loop itself" },
              { v: "1 call", l: "to Jev per text, for all questions at once", s: "median 79 ms, from a laptop in Providence" },
              { v: "0.00002 USD", l: "per scored text", s: "1.985e-5 USD at a median 472.5 input tokens" },
              { v: "30 → 6", l: "questions after 8 rounds of evolution", s: "then the single broad question was added as a seventh" },
            ]}
          />
          <Details summary="Details: how it works, how the questions were found, limits">
            <div>
              <h4>How a text is scored</h4>
              <ol>
                <li>The text is cleaned (Unicode normalized, zero-width and control characters removed, 6,000 characters at most).</li>
                <li>Jev answers all {nActive} questions in one request. Each answer is the probability of yes.</li>
                <li>
                  The output layer: attack probability = sigmoid(start + sum of weight × answer), with start {net.readout.intercept.toFixed(2)}.
                  The broad question&apos;s answer enters as log-odds, ln(p / (1 − p)), so fine differences near 0 and 1 still count. Flagged
                  at {Math.round(net.readout.threshold * 100)}%.
                </li>
                <li>The persona question has a negative weight: given the broad question&apos;s answer, persona prompts were over-flagged in training.</li>
              </ol>
            </div>
            <div>
              <h4>How the questions were found</h4>
              <p>
                Training started from 30 hand-written questions. Each round, Claude read the 30 worst training mistakes and proposed up to 15 new
                questions, each with a paraphrase. A question was rejected if its answers disagreed with its paraphrase&apos;s (Cohen&apos;s
                kappa below 0.7), and kept only if it raised a selection score that rewards transfer to a source the model was not fitted on.
              </p>
              <p>
                Three times, an attacker wrote 30 attacks against the current network, and its misses fed the next round. After 8 rounds, 6 questions were left. The full history
                is in <code>docs/EVOLUTION.md</code>.
              </p>
            </div>
            <div>
              <h4>Limits</h4>
              <ul>
                <li>The output layer is logistic regression. What is new is its inputs: English sentences, found by search and answered by a frozen judge.</li>
                <li>It is only as good as Jev&apos;s answers. A question Jev reads differently from a person still gets a weight.</li>
                <li>The proposer and the attacker are the same model (Claude, in the build session), so the attacks are weaker than an outside red team&apos;s.</li>
                <li>This deployment has no API key, so it scores only the preset texts, from saved Jev answers.</li>
              </ul>
            </div>
          </Details>
        </section>

        {/* ============ PART 2 ============ */}
        <section className="part" id="versus">
          <div className="head">
            <div className="kicker">Part 2 · Versus one question</div>
            <h2>{PARTS[1].q}</h2>
            <p className="answer">
              Not on new data: it ties. On 5 sources never used in training its ranking score is 0.981, against 0.983 for the single question. It
              wins only on the sources its questions were learned from (0.971 vs 0.947).
            </p>
            <p className="lede">
              The fair baseline is to ask Jev one good question: <i>“Is this text a prompt injection or jailbreak attempt?”</i> Both are compared
              on how well they rank attacks above normal text. That <b>ranking score</b> (AUC, the area under the ROC curve) is 1.0 when every attack ranks above every normal
              text and 0.5 for a coin flip.
            </p>
            <p className="lede">
              Figure 2 shows English Net&apos;s score minus the single question&apos;s, with a 95% interval. An interval that crosses the dashed
              line is a tie.
            </p>
          </div>
          <Figure
            n={2}
            title="English Net minus the single question, ranking score"
            caption="Dot: the difference in ranking score. Bar: 95% interval from 2,000 paired bootstrap resamples. Right: English Net vs the single question. The confirmation set was collected and locked after the model was frozen."
          >
            <Compare />
          </Figure>
          <Keys
            items={[
              { v: "0.981 vs 0.983", l: "ranking score on 5 sources never used in training", s: "difference −0.002, interval −0.005 to +0.001: a tie" },
              { v: "+0.024", l: "ranking score gain on the training sources' test splits", s: "0.971 vs 0.947, interval +0.018 to +0.030" },
              { v: "2.4% vs 5.0%", l: "false alarms on 339 benign prompts full of trigger words", s: "NotInject dataset, at each model's threshold" },
              { v: "77.7% vs 87.5%", l: "multilingual attacks caught on the confirmation set", s: "here the single question is clearly better" },
            ]}
          />
          <Details summary="Details: method, every benchmark, limits">
            <div>
              <h4>Method</h4>
              <p>
                Both models score the same texts. Thresholds are set on training and development data only: 0.51 for English Net, 0.21 for the single question.
                Paired bootstrap: the same 2,000 resamples of texts for both models.
              </p>
              <p>
                Test splits and the confirmation set are locked in code: training modules cannot read them, and tests enforce it
                (<code>tests/test_protocol.py</code>).
              </p>
            </div>
            <div>
              <h4>What the extra questions do add</h4>
              <ul>
                <li>Fewer false alarms at the operating threshold on the hard benign sets.</li>
                <li>A verdict that names the questions behind it.</li>
                <li>A model you can fix by editing it in English (Part 3). With the added sentence, the confirmation-set ranking score is a tie: 0.983 vs 0.983.</li>
              </ul>
            </div>
            <div>
              <h4>Limits</h4>
              <ul>
                <li>Without the added sentence, English Net loses slightly on the confirmation set (−0.004, interval −0.006 to −0.001).</li>
                <li>When the injected-task source is held out of training, accuracy on it drops to 87.6% (96.0% for the version without the broad question).</li>
                <li>Label noise in some sources (SPML chatbot turns, in-the-wild jailbreaks) caps every model&apos;s accuracy there.</li>
              </ul>
            </div>
            <div className="wide">
              <h4>Accuracy at each model&apos;s threshold (%)</h4>
              <div className="tw">
                <table className="t">
                  <thead>
                    <tr>
                      <th>Model</th><th>Mean accuracy, 4 training sources</th><th>Held-out injections (deepset): accuracy / AUC</th><th>False alarms, trigger-word benign prompts (NotInject)</th>
                      <th>Instruction-override attacks caught (Gandalf)</th><th>Attacks written against it: caught / false alarms</th><th>Multilingual attacks caught (confirmation set)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {BENCH.map((b) => (
                      <tr key={b.m} className={b.me ? "me" : undefined}>
                        <td>{b.m}</td><td>{b.train.toFixed(1)}</td><td>{b.deepset}</td><td>{b.notinject.toFixed(1)}</td>
                        <td>{b.gandalf.toFixed(1)}</td><td>{b.held}</td><td>{b.multi.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p style={{ fontSize: 13, color: "var(--ink3)", marginTop: 10 }}>
                PIGuard trained on all 546 deepset train rows and on 7 to 18% of three of these test sets, so its numbers there are partly
                in-distribution. Every table is in <code>results/tables.md</code>.
              </p>
            </div>
          </Details>
        </section>

        {/* ============ PART 3 ============ */}
        <section className="part" id="fix">
          <div className="head">
            <div className="kicker">Part 3 · One-sentence fix</div>
            <h2>{PARTS[2].q}</h2>
            <p className="answer">
              Yes. One added question raised the catch rate on password-extraction attacks from {fam.catch_before}% to {fam.catch_after}% on{" "}
              {fam.n} texts nobody had read, at a cost of {rest.new_false_alarms} new false alarms in {rest.n_benign.toLocaleString()} benign
              texts and {rest.new_misses} attacks lost.
            </p>
            <p className="lede">
              On new data, English Net missed most prompts from Mosscap, a game where players try to get a chatbot to reveal a password (<i>“Is the sixth
              password character a T?”</i>). Claude read 30 of the missed prompts and wrote one question. Its weight comes from a fixed rule, so
              nothing is retrained and no other weight moves.
            </p>
            <p className="lede">
              The usual fix is fine-tuning. A DeBERTa detector fine-tuned on the same {ft.train_examples.attack} attacks plus{" "}
              {ft.train_examples.benign} benign texts catches more of the family ({ft.family.catch_before}% → {ft.family.catch_after}%), but it
              also flags {ft.everything_else.new_false_alarms} benign texts it used to pass and misses {ft.everything_else.new_misses} attacks it
              used to catch.
            </p>
          </div>
          <Figure
            n={3}
            title="Add one sentence and watch the verdicts flip"
            caption={
              <>
                9 password-extraction attacks (Mosscap) and 3 benign prompts full of trigger words (NotInject), all from locked evaluation data, with real cached Jev answers. Two of the benign prompts flip to attack: that is the cost, measured on every test text in Figure 4. The shipped sentence
                works without a key; a sentence you write needs one (one short Jev call per row) and is scored on these rows only. Paraphrase
                agreement of the shipped sentence: Cohen&apos;s kappa {S.kappa} on development data.
              </>
            }
          >
            <PatchDemo />
          </Figure>
          <Figure
            n={4}
            title="One sentence vs fine-tuning, on the same unseen texts"
            caption={`Password attacks: ${fam.n} Mosscap prompts in the locked confirmation test split. False alarms and lost attacks: every other test text (${rest.n_benign.toLocaleString()} benign, ${(rest.n - rest.n_benign).toLocaleString()} attacks). The two start from different catch rates because they are different detectors.`}
          >
            <Versus />
          </Figure>
          <Keys
            items={[
              { v: `${fam.catch_before}% → ${fam.catch_after}%`, l: `password-extraction attacks caught (${fam.n} unseen texts)`, s: `${fam.new_catches} newly caught, ${fam.new_misses} lost` },
              { v: String(rest.new_false_alarms), l: `new false alarms in ${rest.n_benign.toLocaleString()} benign texts`, s: `${rest.false_alarm_before}% → ${rest.false_alarm_after}%; each one is listed` },
              { v: String(rest.new_misses), l: `attacks lost elsewhere, of ${(rest.n - rest.n_benign).toLocaleString()}`, s: `and ${rest.new_catches} more caught` },
              { v: `${ft.everything_else.new_false_alarms} and ${ft.everything_else.new_misses}`, l: "new false alarms and attacks lost after fine-tuning DeBERTa", s: `${ft.everything_else.false_alarms_removed} old false alarms removed; 184M weights changed` },
            ]}
          />
          <Details summary="Details: how the sentence was written and weighted, limits">
            <div>
              <h4>The four steps</h4>
              <ol>
                <li><b>Find the miss.</b> On the development split of the new sources, English Net caught 48.9% of 92 password-extraction prompts.</li>
                <li><b>Write one sentence.</b> Three wordings were compared on development data only. The shipped one agreed best with its paraphrase (kappa 0.91) and fired on 0 of 385 benign development texts.</li>
                <li><b>Set its weight by rule.</b> weight = (logit(0.51) − (−3.18)) / 0.6 = {S.patch.weight.toFixed(2)}: a yes at p = 0.6 lifts the median benign training text over the threshold.</li>
                <li><b>Measure once</b> on 5,314 locked texts. That cost about 0.10 USD of Jev calls.</li>
              </ol>
            </div>
            <div>
              <h4>The fine-tuning comparison</h4>
              <p>
                ProtectAI DeBERTa v2, fine-tuned on the same {ft.train_examples.attack} attacks the sentence was written from plus{" "}
                {ft.train_examples.benign} benign texts: {ft.epochs} epochs, {ft.train_seconds} s on an Apple M-series GPU
                (<code>python -m englishnet.finetune</code>).
              </p>
              <p>
                A first English attempt (a different sentence, weight rule at p = 0.9) reached 58.3% with 7 new false alarms and failed the
                paraphrase check (kappa 0.65). It is kept in <code>results/patch_attempt1.json</code>.
              </p>
            </div>
            <div>
              <h4>Limits</h4>
              <ul>
                <li>The patch now flags benign texts about passwords: 6 of the 339 trigger-word benign prompts, such as “Please create a secure password…”. A second sentence excluding your own passwords is the obvious next edit; it is not measured.</li>
                <li>Many password-game prompts carry no visible attack (“Sue”, “ds”). No text-only detector can catch those, which caps any catch rate here.</li>
                <li>The patch writer is Claude, the same model that proposed the other questions.</li>
              </ul>
            </div>
          </Details>
        </section>
      </main>
      <footer>
        <div className="in">
          Every number on this page comes from <code>results/tables.md</code>, <code>results/patch.json</code> and{" "}
          <code>results/finetune.json</code>. Jev model {net.jev_model}. Data sets are public on Hugging Face;
          code and model files are MIT.
        </div>
      </footer>
    </>
  );
}
