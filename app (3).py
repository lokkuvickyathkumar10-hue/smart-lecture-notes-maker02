import streamlit as st
from notes_engine import generate_notes, make_quiz
from audio_tools import transcribe_audio

st.set_page_config(page_title="Smart Lecture Notes Maker 25", page_icon="📚", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {font-family: Inter, sans-serif;}
.stApp {background: linear-gradient(135deg,#faf7ff 0%,#f4efff 48%,#ffffff 100%);}
.block-container {max-width: 1180px; padding-top: 2rem;}
.hero {padding: 2.2rem; border-radius: 24px; color: white;
background: linear-gradient(120deg,#5425a8,#8155e8 60%,#a78bfa);
box-shadow: 0 16px 45px rgba(91,45,160,.20);}
.hero h1 {font-size: clamp(2rem,4vw,3.2rem); font-weight:800; margin:0;}
.hero p {font-size:1.08rem; opacity:.94;}
.pill {display:inline-block; background:rgba(255,255,255,.18); padding:.4rem .8rem;
border-radius:99px; margin-bottom:.8rem; font-size:.85rem;}
.feature {background:white; padding:1.1rem; border:1px solid #eee7ff;
border-radius:16px; min-height:125px; box-shadow:0 5px 20px rgba(60,30,100,.05);}
.feature h3 {color:#5425a8; margin-top:0;}
.stButton>button {background:linear-gradient(90deg,#642db5,#8b5cf6);color:white;
border:0;border-radius:12px;padding:.55rem 1.1rem;font-weight:700;}
.stButton>button:hover {color:white;border:0;filter:brightness(1.08);}
[data-testid="stSidebar"] {background:#f3edff;}
h1,h2,h3 {color:#32145f;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 📚 Smart Notes 25")
    page = st.radio("Navigate", ["Home", "Create Notes", "Record / Upload Audio", "Take a Test"])
    st.markdown("---")
    st.caption("Turn Every Lecture into Smart Notes.")

if page == "Home":
    st.markdown("""
    <div class="hero">
      <span class="pill">STUDY SMARTER • REVISE FASTER</span>
      <h1>Turn Every Lecture into Smart Notes.</h1>
      <p>Transform classroom content into clear, organized notes and quick revision quizzes.</p>
    </div>
    """, unsafe_allow_html=True)
    st.write("")
    c1,c2,c3 = st.columns(3)
    for col, title, desc in [
        (c1,"📝 Smart Notes","Organize lecture text into headings, key points and summaries."),
        (c2,"🎙️ Audio to Notes","Upload a recording or use microphone input where supported."),
        (c3,"🧠 Quick Tests","Create revision questions from your notes.")
    ]:
        with col:
            st.markdown(f'<div class="feature"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
    st.write("")
    st.info("Choose a tool from the left menu to get started.")
    st.markdown("### How it works")
    st.markdown("1. Paste lecture content or provide an audio recording.  \n2. Generate structured notes.  \n3. Review key definitions and summaries.  \n4. Take a short quiz to check your understanding.")

elif page == "Create Notes":
    st.title("📝 Smart Notes Generator")
    st.write("Add your lecture details and content. Your notes will be generated from the text you provide.")
    title = st.text_input("Lecture title", placeholder="e.g. Introduction to Python")
    subject = st.text_input("Subject name", placeholder="e.g. Computer Science")
    content = st.text_area("Paste lecture content", height=260, placeholder="Paste your classroom notes or lecture transcript here...")
    if st.button("✨ Generate Notes", type="primary"):
        if not content.strip():
            st.warning("Please paste some lecture content first.")
        else:
            result = generate_notes(content, title, subject)
            st.session_state["generated_notes"] = result
            st.session_state["quiz_source"] = content
            st.success("Your notes are ready!")
    if st.session_state.get("generated_notes"):
        st.markdown("---")
        st.markdown(st.session_state["generated_notes"])
        st.download_button("⬇️ Download notes as Markdown", st.session_state["generated_notes"],
                           file_name="smart_lecture_notes.md", mime="text/markdown")

elif page == "Record / Upload Audio":
    st.title("🎙️ Lecture Audio")
    st.write("Record audio in supported Streamlit versions, or upload an audio file.")
    audio = None
    if hasattr(st, "audio_input"):
        audio = st.audio_input("Record your lecture")
    uploaded = st.file_uploader("Or upload audio", type=["wav","mp3","m4a","mp4","mpeg","webm"])
    if uploaded:
        st.audio(uploaded)
        audio = uploaded
    st.caption("Audio transcription requires an OpenAI API key and the optional dependencies listed in requirements.txt.")
    if st.button("Transcribe audio"):
        if audio is None:
            st.warning("Record or upload an audio file first.")
        else:
            with st.spinner("Transcribing audio..."):
                transcript, error = transcribe_audio(audio)
            if error:
                st.error(error)
            else:
                st.session_state["transcript"] = transcript
                st.success("Transcription complete.")
    transcript = st.text_area("Transcript (you can edit it)", value=st.session_state.get("transcript",""), height=220)
    if st.button("Generate notes from transcript"):
        if transcript.strip():
            result = generate_notes(transcript, "Recorded lecture", "Lecture")
            st.session_state["generated_notes"] = result
            st.session_state["quiz_source"] = transcript
            st.success("Notes generated. Open Create Notes to view and download them.")
        else:
            st.warning("Add or transcribe some lecture text first.")

elif page == "Take a Test":
    st.title("🧠 Test Your Knowledge")
    source = st.session_state.get("quiz_source", "")
    if not source:
        st.info("Generate notes first, or paste content below to create a quiz.")
        source = st.text_area("Lecture content", height=200)
    count = st.slider("Number of questions", 3, 10, 5)
    if st.button("Generate quiz"):
        if not source.strip():
            st.warning("Please provide lecture content first.")
        else:
            st.session_state["quiz"] = make_quiz(source, count)
            st.session_state["quiz_submitted"] = False
    quiz = st.session_state.get("quiz", [])
    if quiz:
        with st.form("quiz_form"):
            answers = []
            for i, q in enumerate(quiz):
                st.markdown(f"**{i+1}. {q['question']}**")
                answers.append(st.radio("Choose one", q["options"], key=f"q_{i}", index=None, label_visibility="collapsed"))
            submitted = st.form_submit_button("Submit answers")
        if submitted:
            score = sum(1 for a,q in zip(answers,quiz) if a == q["answer"])
            st.success(f"You scored {score} out of {len(quiz)}.")
            for i,(a,q) in enumerate(zip(answers,quiz)):
                st.markdown(f"**Q{i+1}:** {'✅ Correct' if a == q['answer'] else '❌ Correct answer: ' + q['answer']}")
