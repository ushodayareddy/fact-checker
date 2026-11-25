import pytest

from app.agents.language import LanguageAgent, detect_language, dominant_script
from app.state import PipelineState

SAMPLES = {
    "en": "The government announced a new budget for rural roads today.",
    "hi": "सरकार ने आज ग्रामीण सड़कों के लिए नया बजट घोषित किया है।",
    "mr": "सरकारने आज ग्रामीण रस्त्यांसाठी नवीन अर्थसंकल्प जाहीर केला आहे.",
    "bn": "সরকার আজ গ্রামীণ রাস্তার জন্য নতুন বাজেট ঘোষণা করেছে।",
    "ta": "அரசு இன்று கிராமப்புற சாலைகளுக்கான புதிய பட்ஜெட்டை அறிவித்தது.",
    "te": "ప్రభుత్వం ఈ రోజు గ్రామీణ రోడ్ల కోసం కొత్త బడ్జెట్‌ను ప్రకటించింది.",
    "gu": "સરકારે આજે ગ્રામીણ રસ્તાઓ માટે નવું બજેટ જાહેર કર્યું.",
    "kn": "ಸರ್ಕಾರ ಇಂದು ಗ್ರಾಮೀಣ ರಸ್ತೆಗಳಿಗೆ ಹೊಸ ಬಜೆಟ್ ಘೋಷಿಸಿದೆ.",
    "ml": "ഗ്രാമീണ റോഡുകൾക്കായി സർക്കാർ ഇന്ന് പുതിയ ബജറ്റ് പ്രഖ്യാപിച്ചു.",
    "pa": "ਸਰਕਾਰ ਨੇ ਅੱਜ ਪੇਂਡੂ ਸੜਕਾਂ ਲਈ ਨਵਾਂ ਬਜਟ ਐਲਾਨ ਕੀਤਾ ਹੈ।",
    "ur": "حکومت نے آج دیہی سڑکوں کے لیے نیا بجٹ کا اعلان کیا۔",
    "or": "ସରକାର ଆଜି ଗ୍ରାମାଞ୍ଚଳ ରାସ୍ତା ପାଇଁ ନୂଆ ବଜେଟ୍ ଘୋଷଣା କଲେ।",
}


@pytest.mark.parametrize("code,text", SAMPLES.items())
def test_detects_language(code, text):
    assert detect_language(text).code == code


def test_script_detection_ignores_digits_and_punctuation():
    assert dominant_script("123 !!! ???") is None
    assert detect_language("123 !!!").code == "en"


async def test_low_tier_language_adds_warning_and_traces():
    events = []

    async def sink(e):
        events.append(e)

    # Ol Chiki script maps uniquely to Santali, a low-tier language.
    state = PipelineState(raw_input="ᱥᱟᱱᱛᱟᱲᱤ ᱯᱟᱹᱛᱩᱨ", trace=sink)
    state.text = state.raw_input
    await LanguageAgent().run(state)
    assert state.language.code == "sat"
    assert any("low-resource" in w for w in state.warnings)
    assert [e.status for e in events] == ["started", "done"]
