let sessionId = null;
let questionCount = 0;

function startGame() {
  fetch('http://127.0.0.1:8000/api/start_game/')
    .then(response => response.json())
    .then(data => {
      sessionId = data.session_id;
      questionCount = 1;
      showQuestion(data.question);
      document.getElementById('startBtn').style.display = 'none';
      document.getElementById('answers').style.display = 'block';
      updateProgress();
    })
    .catch(err => console.error("Error starting game:", err));
}

function showQuestion(question) {
  document.getElementById('question').innerText = question.text;
}

function updateProgress() {
  document.getElementById('progress').innerText = `Question ${questionCount}`;
}

function submitAnswer(answer) {
  fetch('http://127.0.0.1:8000/api/answer_question/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer: answer })
  })
  .then(response => response.json())
  .then(data => {
    if (data.next_question) {
      questionCount++;
      showQuestion(data.next_question);
      updateProgress();
    } else {
      getResult();
    }
  })
  .catch(err => console.error("Error submitting answer:", err));
}

function getResult() {
  fetch(`http://127.0.0.1:8000/api/get_result/?session_id=${sessionId}`)
    .then(response => response.json())
    .then(data => {
      document.getElementById('question').innerText = '';
      document.getElementById('answers').style.display = 'none';
      document.getElementById('progress').innerText = '';
      document.getElementById('result').innerHTML = `
        <strong>I guess:</strong> ${data.guessed_character.name} <br>
        <em>${data.guessed_character.description || ''}</em>
        ${data.guessed_character.image_url ? `<br><img src="${data.guessed_character.image_url}" width="150">` : ''}
      `;
    })
    .catch(err => console.error("Error getting result:", err));
}
