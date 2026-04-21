document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('.activity-create-form');
    if (!form) {
        return;
    }

    const moduleField = form.querySelector('[name="module"]');
    const titleField = form.querySelector('[name="title"]');
    const submitButton = document.getElementById('course-item-submit');
    const moduleHint = document.getElementById('module-required-hint');
    const selectedType = form.dataset.selectedType || '';
    const attachmentUrlField = form.querySelector('[name="attachment_url"]');
    const attachmentFileField = form.querySelector('[name="attachment_file"]');
    const statementUrlField = form.querySelector('[name="statement_url"]');
    const statementFileField = form.querySelector('[name="statement_file"]');
    const dueDateFields = [
        form.querySelector('[name="due_date_date"]'),
        form.querySelector('[name="due_date_time"]'),
    ].filter(Boolean);
    const maxScoreField = form.querySelector('[name="max_score"]');
    const questionCountField = form.querySelector('[name="question_count"]');
    const quizQuestionList = document.getElementById('quiz-question-list');
    const quizQuestionPagination = document.getElementById('quiz-question-pagination');
    const quizQuestionProgress = document.getElementById('quiz-question-progress');
    const addQuestionButton = document.getElementById('add-quiz-question');
    const imagePreviewUrls = [];
    let activeQuizQuestionIndex = 0;

    if (!moduleField || !submitButton) {
        return;
    }

    window.addEventListener('beforeunload', function () {
        imagePreviewUrls.forEach(function (url) {
            URL.revokeObjectURL(url);
        });
    });

    const requiredFields = [moduleField, titleField, maxScoreField].filter(Boolean);
    requiredFields.forEach(function (field) {
        field.required = true;
    });
    dueDateFields.forEach(function (field) {
        field.required = true;
    });

    const syncAlternativeRequirement = function (primaryField, secondaryField) {
        if (!primaryField || !secondaryField) {
            return;
        }

        const hasPrimaryValue = Boolean(primaryField.value);
        const hasSecondaryValue = Boolean(secondaryField.value);
        const isMissingBoth = !hasPrimaryValue && !hasSecondaryValue;
        const message = 'Preencha um link ou envie um arquivo.';

        primaryField.required = false;
        secondaryField.required = false;
        primaryField.setCustomValidity(isMissingBoth ? message : '');
        secondaryField.setCustomValidity(isMissingBoth ? message : '');
    };

    const hasRequiredPair = function (primaryField, secondaryField) {
        if (!primaryField || !secondaryField) {
            return true;
        }

        return Boolean(primaryField.value) || Boolean(secondaryField.value);
    };

    const syncSubmitAvailability = function () {
        const hasSelectedModule = Boolean(moduleField.value);
        const hasTitle = !titleField || Boolean(titleField.value.trim());
        const hasDueDate = !dueDateFields.length || dueDateFields.every(function (field) {
            return Boolean(field.value);
        });
        const hasMaxScore = !maxScoreField || Boolean(maxScoreField.value);
        const hasAttachmentSource = hasRequiredPair(attachmentUrlField, attachmentFileField);
        const hasStatementSource = hasRequiredPair(statementUrlField, statementFileField);
        const canSubmit = (
            hasSelectedModule
            && hasTitle
            && hasDueDate
            && hasMaxScore
            && hasAttachmentSource
            && hasStatementSource
        );

        submitButton.disabled = !canSubmit;
        submitButton.setAttribute('aria-disabled', String(!canSubmit));

        if (moduleHint) {
            moduleHint.hidden = hasSelectedModule;
        }
    };

    const getQuizCards = function () {
        if (!quizQuestionList) {
            return [];
        }
        return Array.from(quizQuestionList.querySelectorAll('.quiz-builder-card'));
    };

    const renumberQuizQuestions = function () {
        if (!quizQuestionList || !questionCountField) {
            return;
        }

        const cards = getQuizCards();
        questionCountField.value = String(cards.length);

        cards.forEach(function (card, index) {
            const questionNumber = index + 1;
            const headTitle = card.querySelector('[data-question-title]');
            if (headTitle) {
                headTitle.textContent = 'Questão ' + questionNumber;
            }

            card.querySelectorAll('[name], [id], label[for]').forEach(function (element) {
                if (element.hasAttribute('name')) {
                    element.name = element.name.replace(/question_\d+_/g, 'question_' + questionNumber + '_');
                }
                if (element.id) {
                    element.id = element.id.replace(/question_\d+_/g, 'question_' + questionNumber + '_');
                }
                if (element.tagName === 'LABEL' && element.htmlFor) {
                    element.htmlFor = element.htmlFor.replace(/question_\d+_/g, 'question_' + questionNumber + '_');
                }
            });

            const statementLabel = card.querySelector('[data-field-label="statement"]');
            if (statementLabel) {
                statementLabel.innerHTML = 'Pergunta ' + questionNumber + ' <span class="field-required">*</span>';
            }

            const imageLabel = card.querySelector('[data-field-label="image"]');
            if (imageLabel) {
                imageLabel.textContent = 'Imagem da questão (PNG ou JPEG, opcional)';
            }

            const preview = card.querySelector('[data-question-image-preview]');
            if (preview) {
                preview.alt = 'Prévia da imagem da questão ' + questionNumber;
            }
        });
    };

    const renderQuizQuestionPagination = function () {
        const cards = getQuizCards();
        if (!quizQuestionPagination) {
            setActiveQuizQuestion(activeQuizQuestionIndex);
            return;
        }

        quizQuestionPagination.innerHTML = '';
        const total = cards.length;
        const currentPage = activeQuizQuestionIndex + 1;
        const items = [];

        if (total <= 7) {
            for (let page = 1; page <= total; page += 1) {
                items.push(page);
            }
        } else {
            items.push(1);

            const windowStart = Math.max(2, currentPage - 1);
            const windowEnd = Math.min(total - 1, currentPage + 1);

            if (windowStart > 2) {
                items.push('ellipsis-start');
            }

            for (let page = windowStart; page <= windowEnd; page += 1) {
                items.push(page);
            }

            if (windowEnd < total - 1) {
                items.push('ellipsis-end');
            }

            items.push(total);
        }

        items.forEach(function (item) {
            if (typeof item !== 'number') {
                const ellipsis = document.createElement('span');
                ellipsis.className = 'quiz-page-ellipsis';
                ellipsis.textContent = '...';
                ellipsis.setAttribute('aria-hidden', 'true');
                quizQuestionPagination.appendChild(ellipsis);
                return;
            }

            const dot = document.createElement('button');
            dot.type = 'button';
            dot.className = 'quiz-page-dot';
            dot.textContent = String(item);
            dot.setAttribute('aria-label', 'Ir para a questão ' + item);
            dot.addEventListener('click', function () {
                setActiveQuizQuestion(item - 1);
            });
            quizQuestionPagination.appendChild(dot);
        });

        setActiveQuizQuestion(activeQuizQuestionIndex);
    };

    const setActiveQuizQuestion = function (nextIndex) {
        const cards = getQuizCards();
        if (!cards.length) {
            return;
        }

        const boundedIndex = Math.min(Math.max(nextIndex, 0), cards.length - 1);
        const shouldRefreshPagination = boundedIndex !== activeQuizQuestionIndex;
        activeQuizQuestionIndex = boundedIndex;

        cards.forEach(function (card, index) {
            const isActive = index === boundedIndex;
            card.hidden = !isActive;
            card.classList.toggle('is-active', isActive);
        });

        if (quizQuestionPagination) {
            quizQuestionPagination.querySelectorAll('.quiz-page-dot').forEach(function (dot) {
                const isActive = Number(dot.textContent) === boundedIndex + 1;
                dot.classList.toggle('is-active', isActive);
                dot.setAttribute('aria-current', isActive ? 'page' : 'false');
            });
        }

        if (quizQuestionProgress) {
            quizQuestionProgress.textContent = 'Página ' + (boundedIndex + 1) + ' de ' + cards.length;
        }

        if (shouldRefreshPagination && quizQuestionPagination) {
            renderQuizQuestionPagination();
        }
    };

    const bindQuestionRemoval = function (card) {
        if (!card) {
            return;
        }

        const removeButton = card.querySelector('[data-remove-question]');
        if (!removeButton) {
            return;
        }

        removeButton.addEventListener('click', function () {
            const cards = quizQuestionList ? quizQuestionList.querySelectorAll('.quiz-builder-card') : [];
            if (cards.length <= 1) {
                return;
            }

            const removedIndex = getQuizCards().indexOf(card);
            card.remove();
            renumberQuizQuestions();
            if (activeQuizQuestionIndex >= removedIndex) {
                activeQuizQuestionIndex = Math.max(0, activeQuizQuestionIndex - 1);
            }
            renderQuizQuestionPagination();
            syncSubmitAvailability();
        });
    };

    const bindQuestionImagePreview = function (input) {
        if (!input) {
            return;
        }

        let previewUrl = null;
        const preview = input.parentElement ? input.parentElement.querySelector('[data-question-image-preview]') : null;

        const clearPreview = function () {
            if (previewUrl) {
                URL.revokeObjectURL(previewUrl);
                const previewIndex = imagePreviewUrls.indexOf(previewUrl);
                if (previewIndex >= 0) {
                    imagePreviewUrls.splice(previewIndex, 1);
                }
                previewUrl = null;
            }
            if (preview) {
                preview.hidden = true;
                preview.removeAttribute('src');
            }
        };

        input.addEventListener('change', function () {
            clearPreview();
            const file = input.files && input.files[0];
            if (!file || !preview) {
                return;
            }

            previewUrl = URL.createObjectURL(file);
            imagePreviewUrls.push(previewUrl);
            preview.src = previewUrl;
            preview.hidden = false;
        });
    };

    moduleField.addEventListener('change', syncSubmitAvailability);
    if (titleField) {
        titleField.addEventListener('input', syncSubmitAvailability);
    }
    dueDateFields.forEach(function (field) {
        field.addEventListener('input', syncSubmitAvailability);
        field.addEventListener('change', syncSubmitAvailability);
    });
    if (maxScoreField) {
        maxScoreField.addEventListener('input', syncSubmitAvailability);
    }
    if (attachmentUrlField && attachmentFileField) {
        attachmentUrlField.addEventListener('input', function () {
            syncAlternativeRequirement(attachmentUrlField, attachmentFileField);
            syncSubmitAvailability();
        });
        attachmentFileField.addEventListener('change', function () {
            syncAlternativeRequirement(attachmentUrlField, attachmentFileField);
            syncSubmitAvailability();
        });
        syncAlternativeRequirement(attachmentUrlField, attachmentFileField);
    }
    if (statementUrlField && statementFileField) {
        statementUrlField.addEventListener('input', function () {
            syncAlternativeRequirement(statementUrlField, statementFileField);
            syncSubmitAvailability();
        });
        statementFileField.addEventListener('change', function () {
            syncAlternativeRequirement(statementUrlField, statementFileField);
            syncSubmitAvailability();
        });
        syncAlternativeRequirement(statementUrlField, statementFileField);
    }

    if (selectedType === 'quiz' && addQuestionButton && quizQuestionList && questionCountField) {
        addQuestionButton.addEventListener('click', function () {
            const nextIndex = quizQuestionList.querySelectorAll('.quiz-builder-card').length + 1;
            questionCountField.value = String(nextIndex);

            const wrapper = document.createElement('article');
            wrapper.className = 'quiz-builder-card';
            wrapper.innerHTML = `
                <div class="quiz-builder-head">
                    <strong data-question-title>Questão ${nextIndex}</strong>
                    <button class="ghost-button compact" data-remove-question type="button">Excluir questão</button>
                </div>
                <div class="form-field">
                    <label data-field-label="statement" for="id_question_${nextIndex}_statement">Pergunta ${nextIndex} <span class="field-required">*</span></label>
                    <textarea name="question_${nextIndex}_statement" id="id_question_${nextIndex}_statement" rows="4" placeholder="Digite a pergunta de múltipla escolha." required></textarea>
                </div>
                <div class="form-field">
                    <label data-field-label="image" for="id_question_${nextIndex}_image">Imagem da questão (PNG ou JPEG, opcional)</label>
                    <input type="file" name="question_${nextIndex}_image" id="id_question_${nextIndex}_image" accept=".png,.jpg,.jpeg,image/png,image/jpeg">
                    <img class="quiz-question-upload-preview" data-question-image-preview hidden alt="Prévia da imagem da questão ${nextIndex}">
                </div>
                <div class="activity-form-grid">
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_type">Tipo de questão <span class="field-required">*</span></label>
                        <select name="question_${nextIndex}_type" id="id_question_${nextIndex}_type">
                            <option value="single_choice">Uma resposta</option>
                            <option value="multiple_choice">Múltiplas respostas</option>
                        </select>
                    </div>
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_score">Pontuação da questão <span class="field-required">*</span></label>
                        <input type="number" name="question_${nextIndex}_score" id="id_question_${nextIndex}_score" min="0.01" step="0.01" required>
                    </div>
                </div>
                <div class="activity-form-grid">
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_option_1">Alternativa A <span class="field-required">*</span></label>
                        <input type="text" name="question_${nextIndex}_option_1" id="id_question_${nextIndex}_option_1" required>
                        <label class="checkbox-field activity-checkbox" for="id_question_${nextIndex}_option_1_is_correct">
                            <input type="checkbox" name="question_${nextIndex}_option_1_is_correct" id="id_question_${nextIndex}_option_1_is_correct">
                            <span>Alternativa correta</span>
                        </label>
                    </div>
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_option_2">Alternativa B <span class="field-required">*</span></label>
                        <input type="text" name="question_${nextIndex}_option_2" id="id_question_${nextIndex}_option_2" required>
                        <label class="checkbox-field activity-checkbox" for="id_question_${nextIndex}_option_2_is_correct">
                            <input type="checkbox" name="question_${nextIndex}_option_2_is_correct" id="id_question_${nextIndex}_option_2_is_correct">
                            <span>Alternativa correta</span>
                        </label>
                    </div>
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_option_3">Alternativa C <span class="field-required">*</span></label>
                        <input type="text" name="question_${nextIndex}_option_3" id="id_question_${nextIndex}_option_3" required>
                        <label class="checkbox-field activity-checkbox" for="id_question_${nextIndex}_option_3_is_correct">
                            <input type="checkbox" name="question_${nextIndex}_option_3_is_correct" id="id_question_${nextIndex}_option_3_is_correct">
                            <span>Alternativa correta</span>
                        </label>
                    </div>
                    <div class="form-field">
                        <label for="id_question_${nextIndex}_option_4">Alternativa D <span class="field-required">*</span></label>
                        <input type="text" name="question_${nextIndex}_option_4" id="id_question_${nextIndex}_option_4" required>
                        <label class="checkbox-field activity-checkbox" for="id_question_${nextIndex}_option_4_is_correct">
                            <input type="checkbox" name="question_${nextIndex}_option_4_is_correct" id="id_question_${nextIndex}_option_4_is_correct">
                            <span>Alternativa correta</span>
                        </label>
                    </div>
                </div>
            `;
            quizQuestionList.appendChild(wrapper);
            bindQuestionImagePreview(wrapper.querySelector('input[type="file"]'));
            bindQuestionRemoval(wrapper);
            renumberQuizQuestions();
            activeQuizQuestionIndex = getQuizCards().length - 1;
            renderQuizQuestionPagination();
            syncSubmitAvailability();
        });
    }

    if (quizQuestionList) {
        quizQuestionList.querySelectorAll('input[type="file"]').forEach(bindQuestionImagePreview);
        quizQuestionList.querySelectorAll('.quiz-builder-card').forEach(bindQuestionRemoval);
        renumberQuizQuestions();
        renderQuizQuestionPagination();
    }

    syncSubmitAvailability();

    form.addEventListener('submit', function (event) {
        syncAlternativeRequirement(attachmentUrlField, attachmentFileField);
        syncAlternativeRequirement(statementUrlField, statementFileField);

        const firstInvalidField = form.querySelector(':invalid');
        if (!firstInvalidField) {
            return;
        }

        event.preventDefault();
        const invalidQuizCard = firstInvalidField.closest('.quiz-builder-card');
        if (invalidQuizCard && quizQuestionList) {
            const invalidQuizCardIndex = getQuizCards().indexOf(invalidQuizCard);
            if (invalidQuizCardIndex >= 0) {
                setActiveQuizQuestion(invalidQuizCardIndex);
            }
        }
        firstInvalidField.scrollIntoView({ behavior: 'smooth', block: 'center' });
        firstInvalidField.focus({ preventScroll: true });

        if (selectedType === 'quiz') {
            firstInvalidField.reportValidity();
        }
    });
});
