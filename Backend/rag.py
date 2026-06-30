import logging
from typing import List, Dict, Any, Optional
from .services.pinecone_service import PineconeService
from .services.groq_service import GroqService
from .models import User

logger = logging.getLogger("RAG")

# Initialize services
pinecone_service = PineconeService()
groq_service = GroqService()

SYSTEM_PROMPT = (
    "You are an Internal Benefits and SOP Assistant. "
    "Rules:\n"
    "1. Answer only from retrieved company documents.\n"
    "2. Use employee profile context when relevant to generate personalized responses.\n"
    "3. Never reveal unauthorized information.\n"
    "4. Respect role-based access restrictions.\n"
    "5. Never fabricate information.\n"
    "6. If the information is not available in the provided context, you must respond exactly: "
    "\"I couldn't find relevant information in the approved company documents. Would you like to create an HR support ticket?\"\n"
)

def build_context(matches: List[Dict[str, Any]]) -> tuple[str, List[str]]:
    """
    Constructs the context text and extracts source citations.
    """
    if not matches:
        return "", []

    context_parts = []
    citations = []
    
    for match in matches:
        text = match.get("text", "")
        doc_name = match.get("document_name", "Unknown Document")
        doc_type = match.get("document_type", "Policy")
        
        # Build block
        context_parts.append(f"Source: {doc_name} ({doc_type})\nContent: {text}\n---")
        
        citation_str = f"{doc_name} ({doc_type})"
        if citation_str not in citations:
            citations.append(citation_str)

    return "\n\n".join(context_parts), citations

def get_rbac_filter(user_role: str) -> Dict[str, Any]:
    """
    Builds the Pinecone metadata filter based on user roles:
    - Employee Access: Employee documents
    - HR Access: Employee + HR documents
    - Admin Access: Employee + HR + Admin documents
    """
    if user_role == "Employee":
        return {"access_level": {"$in": ["Employee"]}}
    elif user_role == "HR Manager":
        return {"access_level": {"$in": ["Employee", "HR"]}}
    elif user_role == "Admin":
        return {"access_level": {"$in": ["Employee", "HR", "Admin"]}}
    else:
        # Fallback to most restrictive
        return {"access_level": {"$in": ["Employee"]}}

def generate_followup_questions(query_text: str, context: str, user_profile: str, model_key: str = "llama3") -> List[str]:
    """
    Dynamically generates 3-5 intelligent, context-aware follow-up questions.
    """
    if not context:
        prompt = (
            f"The employee asked: '{query_text}' but no direct matching document context was found.\n"
            f"Generate exactly 3 to 5 logical, relevant HR, platform support, or benefits-related follow-up questions they might ask next. "
            f"Respond ONLY as a plain list with one question per line, starting with a bullet point '• '. Do not write any intro or outro."
        )
        system_prompt = "You are a helpful HR system assistant. Generate a list of relevant follow-up questions based on the user's query."
    else:
        prompt = (
            f"Based on the employee's query: '{query_text}' and the retrieved company context:\n{context}\n"
            f"And the employee profile details:\n{user_profile}\n\n"
            f"Generate exactly 3 to 5 logical, context-aware, relevant follow-up questions that the employee might ask next. "
            f"Do not fabricate any details. Respond ONLY as a plain list with one question per line, starting with a bullet point '• '. Do not write any intro or outro."
        )
        system_prompt = "You are a helpful HR system assistant. Generate a list of follow-up questions based on the retrieved context."
    
    try:
        response = groq_service.generate_completion(
            system_prompt=system_prompt,
            user_prompt=prompt,
            model_key=model_key
        )
        lines = response.split("\n")
        questions = []
        for line in lines:
            cleaned = line.strip().lstrip("•").strip().lstrip("-").strip().lstrip("*").strip()
            if cleaned and (cleaned.endswith("?") or len(cleaned) > 10):
                questions.append(cleaned)
        # Return unique list
        unique_questions = []
        for q in questions:
            if q not in unique_questions:
                unique_questions.append(q)
        if unique_questions:
            return unique_questions[:5]
        raise ValueError("No valid questions parsed from LLM response.")
    except Exception as e:
        logger.error(f"Error generating follow-up questions: {e}")
        if not context:
            return [
                "How do I submit an HR ticket?",
                "What is the status of my tickets?",
                "Who can I contact for human support?"
            ]
        else:
            return [
                "Can you tell me more about this policy?",
                "What are the requirements for approval?",
                "Where can I find the official form?"
            ]

def query_rag(query_text: str, current_user: User, model_key: str = "llama3", target_language: str = "english") -> Dict[str, Any]:
    """
    Complete RAG workflow:
    1. Detect language of the query and map user requested target language.
    2. Determine RBAC metadata filter.
    3. Query Pinecone similarity search with top_k=10.
    4. Calculate confidence scoring metrics.
    5. Fetch employee profile and inject it into the prompt context.
    6. Generate response from Groq LLM in the target language.
    7. Generate follow-up questions in the target language.
    8. Check for escalation flags.
    """
    # 1. Target Language determination & Translation
    target_lang_mapped = "English"
    if target_language:
        lang_lower = target_language.lower()
        if "telugu" in lang_lower:
            target_lang_mapped = "Telugu"
        elif "hindi" in lang_lower:
            target_lang_mapped = "Hindi"

    is_telugu = any(0x0C00 <= ord(c) <= 0x0C7F for c in query_text)
    is_hindi = any(0x0900 <= ord(c) <= 0x097F for c in query_text)
    
    if is_telugu:
        detected_lang = "Telugu"
    elif is_hindi:
        detected_lang = "Hindi"
    else:
        detected_lang = "English"

    # Always translate to English for semantic document retrieval
    if detected_lang != "English":
        translation_prompt = f"Translate the following query to English. Do not add explanations or notes. Return only the direct translation.\nQuery: '{query_text}'"
        translated_query = groq_service.generate_completion(
            system_prompt="You are a precise translator. Translate the text to plain English.",
            user_prompt=translation_prompt,
            model_key="llama3"
        )
        translated_query = translated_query.strip("'\"")
    else:
        translated_query = query_text

    # The final target language for generating the response (user chosen dropdown language takes precedence)
    response_lang = target_lang_mapped if target_language and target_language.lower() != "english" else detected_lang

    # 2. RBAC Filter
    role_name = current_user.role.name
    filter_dict = get_rbac_filter(role_name)
    
    # 3. Retrieve top 10 matching chunks from namespace 'company_policies'
    matches = pinecone_service.query_namespace(
        query_text=translated_query,
        namespace="company_policies",
        top_k=10,
        filter_dict=filter_dict
    )

    # 4. Confidence Score Calculation
    max_sim_score = max([m.get("score", 0.0) for m in matches]) if matches else 0.0
    # Map typical cosine similarity (0.3 - 0.75) of all-MiniLM-L6-v2 model to a 0.0 - 1.0 scale
    normalized_sim = (max_sim_score - 0.3) / 0.45
    normalized_sim = max(0.0, min(1.0, normalized_sim))

    # Context relevance based on query keywords matching context
    stop_words = {"what", "is", "the", "are", "how", "many", "do", "i", "get", "can", "we", "for", "in", "on", "of", "a", "an", "to", "with", "have", "you"}
    query_words = [w.lower().strip("?,.!") for w in translated_query.split() if w.lower().strip("?,.!") not in stop_words and len(w) > 2]
    if query_words and matches:
        all_context_text = " ".join([m.get("text", "").lower() for m in matches])
        matched_words = sum(1 for w in query_words if w in all_context_text)
        relevance_val = matched_words / len(query_words)
    else:
        relevance_val = 1.0 if matches else 0.0

    # Chunk quality based on average length
    avg_len = sum(len(m.get("text", "")) for m in matches) / len(matches) if matches else 0
    if avg_len >= 300:
        quality_val = 1.0
    elif avg_len >= 150:
        quality_val = 0.8
    elif avg_len > 0:
        quality_val = 0.5
    else:
        quality_val = 0.0

    if matches:
        raw_score = (normalized_sim * 0.6 + relevance_val * 0.2 + quality_val * 0.2) * 100
        confidence_score = int(max(10, min(100, raw_score)))
    else:
        confidence_score = 0

    if confidence_score >= 80:
        confidence_level = "High Confidence"
    elif confidence_score >= 55:
        confidence_level = "Medium Confidence"
    else:
        confidence_level = "Low Confidence"

    # Hallucination prevention fallback if matches are empty
    if not matches:
        if response_lang == "Telugu":
            fallback_ans = "ఆమోదించబడిన కంపెనీ పత్రాలలో నాకు సంబంధిత సమాచారం కనుగొనబడలేదు. మీరు హెచ్ఆర్ సపోర్ట్ టికెట్‌ను సృష్టించాలనుకుంటున్నారా?"
        elif response_lang == "Hindi":
            fallback_ans = "मुझे स्वीकृत कंपनी दस्तावेजों में प्रासंगिक जानकारी नहीं मिली। क्या आप एक एचआर सहायता टिकट बनाना चाहेंगे?"
        else:
            fallback_ans = "I couldn't find relevant information in the approved company documents. Would you like to create an HR support ticket?"
        return {
            "answer": fallback_ans,
            "citations": [],
            "confidence_score": 0,
            "confidence_level": "Low Confidence",
            "escalate": True,
            "followup_questions": generate_followup_questions(query_text, "", "", model_key)
        }

    # 5. Build context & citations list
    context, citations = build_context(matches)
    
    # User Profile context
    profile_details = (
        f"Employee Profile Details:\n"
        f"- Role/Access Level: {role_name}\n"
        f"- Department: {current_user.department or 'N/A'}\n"
        f"- Designation: {current_user.designation or 'N/A'}\n"
        f"- Employment Type: {current_user.employment_type or 'N/A'}\n"
        f"- Location: {current_user.location or 'N/A'}\n"
        f"- Joining Date: {current_user.joining_date.strftime('%Y-%m-%d') if current_user.joining_date else 'N/A'}\n"
    )

    # 6. Call Groq LLM
    user_prompt = (
        f"{profile_details}\n"
        f"Retrieved Company Documents Context:\n{context}\n\n"
        f"User's Question: {query_text} (In {response_lang})\n\n"
        f"Instructions:\n"
        f"1. Answer the question strictly using the Retrieved Company Documents Context and the Employee Profile Details.\n"
        f"2. Generate your response in the language: {response_lang}.\n"
        f"3. Do not include any confidence metrics or suggested questions inside your generated answer. The system will handle that.\n"
        f"4. If the context does not contain the answer, say exactly: \"I couldn't find relevant information in the approved company documents. Would you like to create an HR support ticket?\"\n"
        f"5. You must explicitly mention the source document name(s) (e.g., 'DocumentName.docx') that you used to find the answer."
    )

    answer = groq_service.generate_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model_key=model_key
    )

    # Double check if the LLM output indicates not found
    not_found_phrases = [
        "couldn't find relevant information",
        "could not find relevant information",
        "information is not available",
        "not found in the approved company documents",
        "support ticket"
    ]
    is_not_found = any(phrase in answer.lower() for phrase in not_found_phrases)
    
    if is_not_found:
        if response_lang == "Telugu":
            answer = "ఆమోదించబడిన కంపెనీ పత్రాలలో నాకు సంబంధిత సమాచారం కనుగొనబడలేదు. మీరు హెచ్ఆర్ సపోర్ట్ టికెట్‌ను సృష్టించాలనుకుంటున్నారా?"
        elif response_lang == "Hindi":
            answer = "मुझे स्वीकृत कंपनी दस्तावेजों में प्रासंगिक जानकारी नहीं मिली। क्या आप एक एचआर सहायता टिकट बनाना चाहेंगे?"
        else:
            answer = "I couldn't find relevant information in the approved company documents. Would you like to create an HR support ticket?"
        citations = []
        confidence_score = 30
        confidence_level = "Low Confidence"
    else:
        # Filter citations to only include those explicitly mentioned in the generated answer
        used_citations = []
        for citation in citations:
            doc_part = citation.split(" (")[0]  # Extracts filename part (e.g. "Doc.docx")
            base_name = doc_part.rsplit(".", 1)[0] if "." in doc_part else doc_part  # Strips extension
            if doc_part.lower() in answer.lower() or base_name.lower() in answer.lower():
                used_citations.append(citation)
        # Fallback to all if none were explicitly mentioned
        if used_citations:
            citations = used_citations

    # 7. Generate follow-up questions
    followups = generate_followup_questions(translated_query, context, profile_details, model_key)
    
    # Translate follow-up questions to query language if necessary
    if response_lang != "English" and followups:
        translated_followups = []
        for q in followups:
            trans_prompt = f"Translate the following English question to {response_lang}. Do not explain or add notes, return only the translated question:\n'{q}'"
            trans_q = groq_service.generate_completion(
                system_prompt="You are a precise translator.",
                user_prompt=trans_prompt,
                model_key=model_key
            )
            translated_followups.append(trans_q.strip("'\""))
        followups = translated_followups

    # 8. Check for escalation
    escalate = False
    if confidence_score < 55 or is_not_found:
        escalate = True
    else:
        # If user explicitly requests human support or ticket creation
        query_lower = query_text.lower()
        if "ticket" in query_lower or "human" in query_lower or "support" in query_lower or "escalat" in query_lower:
            escalate = True

    return {
        "answer": answer,
        "citations": citations,
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "escalate": escalate,
        "followup_questions": followups
    }
