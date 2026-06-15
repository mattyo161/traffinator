"""Grant or change a user's tier (e.g. promote someone to PRO).

There's no billing yet (#35), so PRO is assigned manually. Identify the user by
email (matched case-insensitively).

    python manage.py set_tier alice@example.com PRO
    python manage.py set_tier alice@example.com PRO --sub-tier COMP
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from commute.models import UserProfile
from commute.tiers import FREE, PRO

TIERS = [FREE, PRO]
SUB_TIERS = ["", "TRIAL", "COMP", "USER", "TEAM"]


class Command(BaseCommand):
    help = "Set a user's tier (FREE/PRO) by email."

    def add_arguments(self, parser):
        parser.add_argument("email", help="User email (case-insensitive).")
        parser.add_argument("tier", choices=TIERS, help="Tier to assign.")
        parser.add_argument("--sub-tier", choices=SUB_TIERS, default="",
                            help="Optional PRO sub-tier label (TRIAL/COMP/USER/TEAM).")

    def handle(self, *args, **options):
        users = list(User.objects.filter(email__iexact=options["email"]))
        if not users:
            raise CommandError(f"No user with email {options['email']!r}.")
        if len(users) > 1:
            raise CommandError(f"Multiple users share email {options['email']!r}; resolve in the DB.")
        user = users[0]
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.tier = options["tier"]
        profile.sub_tier = options["sub_tier"]
        profile.save(update_fields=["tier", "sub_tier", "updated_at"])
        label = f"{profile.tier}/{profile.sub_tier}" if profile.sub_tier else profile.tier
        self.stdout.write(self.style.SUCCESS(f"{user.email} -> {label}"))
