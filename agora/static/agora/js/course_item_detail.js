document.addEventListener('DOMContentLoaded', function () {
    const quizForm = document.querySelector('[data-quiz-wizard]');
    if (!quizForm) {
        return;
    }

    const questionCards = Array.from(quizForm.querySelectorAll('[data-quiz-step]'));
    const previousButton = quizForm.querySelector('[data-quiz-previous]');
    const nextButton = quizForm.querySelector('[data-quiz-next]');
    const submitButton = quizForm.querySelector('[data-quiz-submit]');
    const progressLabel = quizForm.querySelector('[data-quiz-progress]');
    let currentStep = 0;

    const syncWizard = function () {
        questionCards.forEach(function (card, index) {
            card.hidden = index !== currentStep;
        });

        if (progressLabel) {
            progressLabel.textContent = 'Questão ' + (currentStep + 1) + ' de ' + questionCards.length;
        }

        if (previousButton) {
            previousButton.hidden = currentStep === 0;
        }
        if (nextButton) {
            nextButton.hidden = currentStep === questionCards.length - 1;
        }
        if (submitButton) {
            submitButton.hidden = currentStep !== questionCards.length - 1;
        }
    };

    if (previousButton) {
        previousButton.addEventListener('click', function () {
            if (currentStep > 0) {
                currentStep -= 1;
                syncWizard();
            }
        });
    }

    if (nextButton) {
        nextButton.addEventListener('click', function () {
            if (currentStep < questionCards.length - 1) {
                currentStep += 1;
                syncWizard();
            }
        });
    }

    syncWizard();
});
