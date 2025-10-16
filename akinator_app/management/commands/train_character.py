from django.core.management.base import BaseCommand, CommandError
from akinator_app.models import Character, Question

class Command(BaseCommand):
    help = 'Manually train the AI on a specific character by answering a series of questions.'

    def add_arguments(self, parser):
        parser.add_argument('character_name', type=str, help='The name of the character to train.')

    def handle(self, *args, **options):
        character_name = options['character_name']
        
        # Find the character or create a new one.
        character, created = Character.objects.get_or_create(
            name__iexact=character_name,
            defaults={'name': character_name, 'added_by': 'manual_training'}
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created new character: '{character.name}'"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Found existing character: '{character.name}'"))

        self.stdout.write(self.style.NOTICE("\n--- Starting Training Session ---"))
        self.stdout.write("Please answer the following questions. Your options are:")
        self.stdout.write("y (yes), n (no), p (probably), pn (probably_not), d (don't know), s (skip)")

        questions = Question.objects.all()
        features_to_update = character.features or {}
        questions_answered = 0

        for question in questions:
            while True:
                # Construct the prompt, showing the existing answer if there is one.
                existing_answer = features_to_update.get(str(question.id))
                prompt = f"\nQ: {question.text}"
                if existing_answer:
                    prompt += self.style.SUCCESS(f" [Current answer: {existing_answer}]")
                prompt += ": "
                
                # Get user input.
                raw_answer = input(prompt).lower().strip()
                
                answer_map = {
                    'y': 'yes',
                    'n': 'no',
                    'p': 'probably',
                    'pn': 'probably_not',
                    'd': 'dont_know',
                    's': None # Skip
                }

                if raw_answer in answer_map:
                    answer = answer_map[raw_answer]
                    if answer is not None:
                        features_to_update[str(question.id)] = answer
                        questions_answered += 1
                    break # Move to the next question
                else:
                    self.stdout.write(self.style.ERROR("Invalid input. Please use one of the specified options."))

        # Save the updated features to the character.
        character.features = features_to_update
        character.save()

        self.stdout.write(self.style.SUCCESS(f"\n--- Training Complete! ---"))
        self.stdout.write(f"Updated {questions_answered} features for '{character.name}'.")
