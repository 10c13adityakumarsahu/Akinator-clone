import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from akinator_app.models import Character, Question
# Import the scraper and the mapping from your other app files
from akinator_app.ai_data_collector import get_character_info
from akinator_app.views import WIKIDATA_TO_QUESTION_MAP

class Command(BaseCommand):
    help = 'Automatically scrapes and trains the AI on a list of character names from a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='The path to the JSON file containing the list of character names.')

    @transaction.atomic
    def handle(self, *args, **options):
        json_file_path = options['json_file']

        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                character_names = json.load(f)
                if not isinstance(character_names, list):
                    raise CommandError('Invalid JSON. The file must contain a single list of strings (character names).')
        except FileNotFoundError:
            raise CommandError(f'File not found at "{json_file_path}"')
        except json.JSONDecodeError:
            raise CommandError('Invalid JSON. Please check the file format.')

        self.stdout.write(self.style.NOTICE(f"--- Starting auto-scraping and training from {json_file_path} ---"))

        characters_updated = 0
        characters_created = 0

        for name in character_names:
            if not isinstance(name, str) or not name.strip():
                self.stdout.write(self.style.WARNING("Skipping invalid or empty name in the list."))
                continue
            
            self.stdout.write(f"Processing '{name}'...")

            # Check if character already exists
            character, created = Character.objects.get_or_create(
                name__iexact=name,
                defaults={'name': name, 'added_by': 'bulk_scrape_script'}
            )

            # Scrape data from external sources
            try:
                scraped_data = get_character_info(name)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   > Could not scrape data for '{name}': {e}"))
                continue

            # Populate the initial features based on the scraped data
            initial_features = character.features or {}
            details = scraped_data.get("details")
            if details:
                for key, value_map in WIKIDATA_TO_QUESTION_MAP.items():
                    detail_value = details.get(key)
                    if detail_value and detail_value.lower() in value_map:
                        mapping = value_map[detail_value.lower()]
                        
                        # --- MODIFIED: Get question text from ID ---
                        q_id = mapping["question_id"]
                        if q_id != -1:
                            try:
                                # We fetch the question text to use it as the key
                                question = Question.objects.get(id=q_id)
                                initial_features[question.text] = mapping["answer"]
                            except Question.DoesNotExist:
                                self.stdout.write(self.style.ERROR(f"  > Error: Question ID {q_id} in WIKIDATA_TO_QUESTION_MAP not found in database. Skipping."))
                        # --- END MODIFIED ---
            
            # Update character details
            character.description = scraped_data.get("summary", character.description or "")
            character.features = initial_features
            character.save()
            
            if created:
                characters_created += 1
                self.stdout.write(self.style.SUCCESS(f"   > Created and trained new character: '{name}'"))
            else:
                characters_updated += 1
                self.stdout.write(self.style.SUCCESS(f"   > Updated existing character: '{name}' with scraped data."))

        self.stdout.write(self.style.SUCCESS("\n--- Bulk Training Complete! ---"))
        self.stdout.write(f"Characters Created: {characters_created}")
        self.stdout.write(f"Characters Updated: {characters_updated}")
