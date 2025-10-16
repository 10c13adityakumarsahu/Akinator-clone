let session_id = null;

const startBtn = document.getElementById("start-btn");
const questionContainer = document.getElementById("question-container");
const questionText = document.getElementById("question-text");
const answerBtns = document.querySelectorAll(".answer-btn");
const resultContainer = document.getElementById("result-container");
const resultName = document.getElementById("result-name");
const resultDesc = document.getElementById("result-desc");
const restartBtn = document.getElementById("restart-btn");

startBtn.addEventListener("click", startGame);
restartBtn.addEventListener("click", () => location.reload());

function startGame() {
    fetch("/api/start_game/")
    .then(res => res.json())
    .then(data => {
        session_id = data.session_id;
        showQuestion(data.question);
        startBtn.classList.add("hidden");
        questionContainer.classList.remove("hidden");
    });
}

answerBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        const answer = btn.getAttribute("data-answer");
        fetch("/api/answer/", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({session_id, answer})
        })
        .then(res => res.json())
        .then(data => {
            if (data.next_question) {
                showQuestion(data.next_question);
            } else if (data.guessed_character) {
                showResult(data.guessed_character);
            } else if (data.message) {
                questionText.textContent = data.message;
                answerBtns.forEach(b => b.disabled = true);
            }
        });
    });
});

function showQuestion(q) {
    questionText.textContent = q.text;
}

function showResult(character) {
    questionContainer.classList.add("hidden");
    resultContainer.classList.remove("hidden");
    resultName.textContent = character.name;
    resultDesc.textContent = character.description;
}
