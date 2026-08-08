"""Create Local Understanding v1 source-design artifacts; never training rows."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "local_understanding" / "blueprint"

LABELS = {
    "GOAL_LIST_QUERY": (40, ["Məqsədlərim nədir?", "Mənim hansı məqsədlərim var?", "Hazırda nəyə çatmağa çalışıram?"], "PERSONAL_ASSERTION, GOAL_WRITE_REQUEST, GENERAL_CONVERSATION"),
    "IDENTITY_QUERY": (35, ["Sən kimsən?", "Adın nədir?", "Özünü tanıt."], "PERSONAL_PROFILE_QUERY, GENERAL_CONVERSATION"),
    "PERSONAL_FACT_QUERY": (50, ["Ən sevdiyim anime hansıdı?", "Mən hansı oyunu sevirəm?", "Sevdiyim rəng nə idi?"], "PERSONAL_PROFILE_QUERY, PERSONAL_ASSERTION, GENERAL_CONVERSATION"),
    "PERSONAL_PROFILE_QUERY": (40, ["Mənim haqqımda nə bilirsən?", "Məni necə tanıyırsan?", "Mənimlə bağlı bildiklərini de."], "PERSONAL_FACT_QUERY, IDENTITY_QUERY, UNKNOWN"),
    "MEMORY_WRITE_REQUEST": (45, ["Bunu yadda saxla.", "Bunu unutma.", "Gələcək üçün bunu xatırla."], "PERSONAL_ASSERTION, GENERAL_CONVERSATION, UNKNOWN"),
    "GOAL_WRITE_REQUEST": (60, ["C1-i məqsəd kimi əlavə et.", "Bu məqsədi dayandır.", "Alman dili məqsədimi dəyiş."], "GOAL_LIST_QUERY, PERSONAL_ASSERTION, UNKNOWN"),
    "PERSONAL_ASSERTION": (80, ["Ən sevdiyim anime AoT-dir.", "Mən Alman dili öyrənirəm.", "Mən MK11-i sevirəm."], "GOAL_LIST_QUERY, PERSONAL_FACT_QUERY, GENERAL_CONVERSATION"),
    "GENERAL_CONVERSATION": (120, ["Gemini nədir?", "Bleach necə animedir?", "Kod yaza bilirsən?"], "all authority labels"),
}

TOPICS = ["anime", "oyun", "kitab", "yemək", "dil öyrənmə", "təhsil", "texnologiya", "hobbi", "peşə", "səyahət", "musiqi", "gündəlik seçim"]
CONSTRUCTIONS = ["direct_wh", "indirect_request", "inventory", "current_focus", "recall_framing", "polite_request", "omitted_subject", "word_order_variant", "informal_question", "explicit_scope"]
GENERAL_AREAS = ["public_knowledge", "science", "medicine", "mathematics", "technology", "programming", "entertainment", "definitions", "comparisons", "recommendations", "explanations", "translation", "summarization", "creative_writing", "capability", "hypothetical", "casual", "opinion", "study_help", "grammar"]

def family(label, index, examples, neighbors):
    topic = TOPICS[index % len(TOPICS)]
    construction = CONSTRUCTIONS[index % len(CONSTRUCTIONS)]
    if label == "GENERAL_CONVERSATION":
        area = GENERAL_AREAS[index % len(GENERAL_AREAS)]
        definition = f"Public/provider conversation about {area}; no claim about the user's stored state."
        construction = f"{area}_{construction}"
    elif label == "GOAL_WRITE_REQUEST":
        operation = ("create", "add", "change", "rename", "pause", "resume", "complete", "retire", "reprioritize", "clarify")[index % 10]
        definition = f"Natural-language request to {operation} a clearly owned goal; guidance only."
    elif label == "PERSONAL_ASSERTION":
        statement = ("preference", "dislike", "characteristic", "activity", "plan", "goal_statement", "study", "habit", "ownership", "use", "correction", "change_of_mind")[index % 12]
        definition = f"First-person {statement} statement about the user, never a write instruction."
    else:
        definition = f"{label.replace('_', ' ').title()} expressed through {construction} about {topic}."
    base = examples[index % len(examples)]
    reps = [base, base.rstrip("?.") + " mənə de.", base.rstrip("?.") + " zəhmət olmasa.", base.lower(), base.replace("ə", "e").replace("ı", "i")]
    forbidden = ["Keçən dəfə sənə nə demişdim?", "Dünən nə danışmışdıq?", "Yaddaşında bu barədə nə var?"]
    if label == "GOAL_WRITE_REQUEST": forbidden += ["Sil bunu.", "Dəyiş.", "Dayandır."]
    return {"family_id": f"{label}-F{index:03d}", "intent_label": label, "semantic_definition": definition, "construction_type": construction, "representative_clean_examples": reps, "hardest_neighboring_intents": neighbors.split(", "), "hard_negative_contrast_examples": ["Məqsəd qoymaq faydalıdırmı?", "Məqsədim C1 olmaqdır.", "C1-i məqsəd kimi əlavə et."], "allowed_registers": ["standard", "conversational", "baku_internet", "mobile_typing"], "allowed_noise": ["diacritic_removal", "punctuation", "capitalization", "single_realistic_typo"], "context_policy": "context_may_help_only_for_explicit_short_followup", "entity_substitution_safe": label not in {"IDENTITY_QUERY", "PERSONAL_PROFILE_QUERY"}, "ambiguity_risks": ["scope ambiguity", "personal-vs-general overlap"], "must_not_generate": forbidden, "topic_domain": topic}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    families=[]
    for label,(count,examples,neighbors) in LABELS.items():
        families.extend(family(label, i, examples, neighbors) for i in range(1,count+1))
    (OUT/"source_families.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in families)+"\n",encoding="utf-8")
    pairs=[("GOAL_LIST_QUERY","PERSONAL_ASSERTION"),("GOAL_LIST_QUERY","GOAL_WRITE_REQUEST"),("GOAL_LIST_QUERY","GENERAL_CONVERSATION"),("IDENTITY_QUERY","PERSONAL_PROFILE_QUERY"),("IDENTITY_QUERY","GENERAL_CONVERSATION"),("PERSONAL_FACT_QUERY","PERSONAL_PROFILE_QUERY"),("PERSONAL_FACT_QUERY","PERSONAL_ASSERTION"),("PERSONAL_FACT_QUERY","GENERAL_CONVERSATION"),("PERSONAL_PROFILE_QUERY","UNKNOWN"),("MEMORY_WRITE_REQUEST","GENERAL_CONVERSATION"),("MEMORY_WRITE_REQUEST","PERSONAL_ASSERTION"),("GOAL_WRITE_REQUEST","UNKNOWN"),("PERSONAL_ASSERTION","GENERAL_CONVERSATION")]
    matrix=[{"contrast_id":f"HN-{i:03d}","positive":a,"negative":b,"coverage":"required","examples":["Məqsədlərim nədir?","Məqsədim C1 olmaqdır.","Məqsəd qoymaq faydalıdırmı?"]} for i,(a,b) in enumerate(pairs,1)]
    (OUT/"hard_negative_matrix.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in matrix)+"\n",encoding="utf-8")
    context=[{"context_id":f"CTX-{i:02d}","current":text,"policy":policy,"rule":"previous exchange is evidence only; never upgrades to write authority"} for i,(text,policy) in enumerate([("davam et","context_helps"),("bəs o?","context_helps"),("bunu yadda saxla","current_intent_sufficient"),("bəs məqsədlərim?","context_helps"),("onda dəyiş","challenge_reject"),("Bəs?","challenge_reject")],1)]
    (OUT/"context_blueprint.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False,sort_keys=True) for x in context)+"\n",encoding="utf-8")
    plan={label:{"target":1600 if label=="GENERAL_CONVERSATION" else 800,"families":count,"allocation":"risk-weighted; minimum 8, maximum 24 source rows per family"} for label,(count,_,_) in LABELS.items()}
    (OUT/"generation_plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (OUT/"blueprint_report.md").write_text("# Local Understanding v1 Source Blueprint\n\nThis blueprint defines 470 source families. It is not training data. It must be manually reviewed before source generation; repeated representative examples are placeholders for family-level review, not approved source rows.\n",encoding="utf-8")
    print(len(families), {k:v[0] for k,v in LABELS.items()})
if __name__ == "__main__": main()
