#!/usr/bin/env python3
"""Generate a synthetic student dataset (data/students.csv).

The generator is seeded (RANDOM_SEED in .env, default 42) so the same dataset
is produced on every machine - important for reproducible demos and tests.

Usage:
    uv run python scripts/generate_students.py            # 90 students
    uv run python scripts/generate_students.py --count 120
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

# --------------------------------------------------------------------------- #
# Source vocabulary
# --------------------------------------------------------------------------- #
# Names are kept gender-consistent (Macedonian surnames are gendered:
# Petrov / Petrova), which makes the synthetic dataset look credible.
FIRST_NAMES_F = [
    "Ana", "Elena", "Marija", "Ivana", "Sara", "Teodora", "Kristina", "Jovana",
    "Tamara", "Milena", "Sofija", "Angela", "Natasha", "Emilija", "Katerina",
    "Dragana", "Simona", "Biljana", "Sanja", "Aleksandra", "Monika", "Vesna",
    "Bojana", "Isidora", "Frosina", "Ivona", "Nina", "Dragica",
]

FIRST_NAMES_M = [
    "Marko", "Stefan", "Nikola", "Aleksandar", "Dimitar", "Bojan", "Filip",
    "Andrej", "Viktor", "Damjan", "Petar", "Martin", "Goran", "Blagoj",
    "Vladimir", "Zoran", "Igor", "Darko", "Kiril", "Trajche", "Ljupcho",
    "Hristijan", "Borche", "Mile", "Vasko", "Gjorgji",
]

# Surname stems - the generator appends "ov/ev/ski" or "ova/eva/ska".
SURNAME_STEMS = [
    ("Petr", "ov"), ("Ivan", "ov"), ("Stojan", "ov"), ("Nikol", "ov"),
    ("Trajk", "ovski"), ("Angel", "ov"), ("Dimitr", "ov"), ("Jovan", "ovski"),
    ("Stefan", "ov"), ("Mitr", "ev"), ("Rist", "ov"), ("Kost", "ov"),
    ("Georgi", "ev"), ("Todor", "ovski"), ("Spas", "ov"), ("Mark", "ov"),
    ("Ili", "ev"), ("Boshk", "ov"), ("Velk", "ov"), ("Naum", "ov"),
    ("Krst", "ev"), ("Zdravk", "ovski"), ("Pavl", "ov"), ("Cvetk", "ov"),
    ("Jakim", "ovski"), ("Serafim", "ov"), ("Lazar", "ev"), ("Gjorgji", "ev"),
    ("Bogdan", "ov"), ("Ognen", "ov"),
]

# Male suffix -> female suffix
FEMALE_SUFFIX = {"ov": "ova", "ev": "eva", "ovski": "ovska"}

FACULTIES = [
    "Computer Science",
    "Engineering",
    "Economics",
    "Law",
    "Design",
    "Philology",
]

# Weighted so the dataset is not perfectly uniform - more CS/Engineering
# students, which mirrors a technical faculty's real population.
FACULTY_WEIGHTS = [30, 22, 18, 12, 10, 8]

CATEGORIES = [
    "Technology", "Career", "Business", "Art", "Music", "Sport", "Volunteering",
    "Culture", "Science", "Networking", "Workshop", "Competition", "Health",
    "Student Club", "Language",
]

# Interests students of a given faculty are more likely to pick. The generator
# takes most interests from here and one "wildcard" from the full list, so the
# data stays realistic without becoming deterministic per faculty.
FACULTY_AFFINITY: dict[str, list[str]] = {
    "Computer Science": ["Technology", "Competition", "Workshop", "Science", "Career"],
    "Engineering": ["Technology", "Science", "Workshop", "Competition", "Career"],
    "Economics": ["Business", "Career", "Networking", "Workshop", "Competition"],
    "Law": ["Career", "Networking", "Culture", "Volunteering", "Business"],
    "Design": ["Art", "Culture", "Workshop", "Music", "Technology"],
    "Philology": ["Culture", "Language", "Art", "Volunteering", "Music"],
}

# Campus bounding box around the Skopje university area, matching the
# coordinate range used by the events dataset.
LAT_RANGE = (41.9905, 42.0085)
LON_RANGE = (21.3935, 21.4360)

# (available_from, available_to) windows a student realistically has free.
TIME_WINDOWS = [
    ("08:00", "12:00"),
    ("09:00", "15:00"),
    ("10:00", "16:00"),
    ("11:00", "17:00"),
    ("12:00", "18:00"),
    ("13:00", "19:00"),
    ("14:00", "20:00"),
    ("15:00", "21:00"),
    ("16:00", "22:00"),
    ("09:00", "21:00"),
]

MAX_PRICES = [0, 0, 0, 5, 5, 10, 10, 15, 20]

HEADER = [
    "student_id", "name", "email", "faculty", "year_of_study",
    "latitude", "longitude", "interests", "available_from", "available_to",
    "max_price",
]


def slugify(text: str) -> str:
    """'Aleksandar Gjorgjiev' -> 'aleksandar.gjorgjiev' (ASCII only)."""
    normalised = unicodedata.normalize("NFKD", text)
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")
    return ".".join(part.lower() for part in ascii_text.split())


def pick_interests(rng: random.Random, faculty: str) -> list[str]:
    """Return 2-4 distinct interests, biased toward the student's faculty."""
    count = rng.choices([2, 3, 4], weights=[25, 50, 25])[0]
    affinity = FACULTY_AFFINITY[faculty]

    chosen: list[str] = rng.sample(affinity, k=min(count - 1, len(affinity)))
    # One wildcard keeps cross-faculty interests in the data.
    wildcard_pool = [c for c in CATEGORIES if c not in chosen]
    chosen.append(rng.choice(wildcard_pool))

    # Preserve insertion order while removing accidental duplicates.
    return list(dict.fromkeys(chosen))


def generate(count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    used_emails: set[str] = set()
    students: list[dict] = []

    for student_id in range(1, count + 1):
        female = rng.random() < 0.5
        first = rng.choice(FIRST_NAMES_F if female else FIRST_NAMES_M)
        stem, suffix = rng.choice(SURNAME_STEMS)
        last = stem + (FEMALE_SUFFIX[suffix] if female else suffix)
        name = f"{first} {last}"

        base_email = f"{slugify(name)}@students.ukim.mk"
        email = base_email
        suffix = 1
        while email in used_emails:
            suffix += 1
            email = f"{slugify(name)}{suffix}@students.ukim.mk"
        used_emails.add(email)

        faculty = rng.choices(FACULTIES, weights=FACULTY_WEIGHTS)[0]
        available_from, available_to = rng.choice(TIME_WINDOWS)

        students.append(
            {
                "student_id": student_id,
                "name": name,
                "email": email,
                "faculty": faculty,
                "year_of_study": rng.choices([1, 2, 3, 4], weights=[30, 28, 24, 18])[0],
                "latitude": round(rng.uniform(*LAT_RANGE), 5),
                "longitude": round(rng.uniform(*LON_RANGE), 5),
                "interests": ",".join(pick_interests(rng, faculty)),
                "available_from": available_from,
                "available_to": available_to,
                "max_price": rng.choice(MAX_PRICES),
            }
        )

    return students


def write_csv(students: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(students)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic student profiles")
    parser.add_argument("--count", type=int, default=90, help="How many students (default: 90)")
    parser.add_argument("--seed", type=int, default=settings.random_seed)
    parser.add_argument("--out", type=Path, default=settings.students_csv)
    args = parser.parse_args()

    students = generate(args.count, args.seed)
    write_csv(students, args.out)

    faculties = {}
    for s in students:
        faculties[s["faculty"]] = faculties.get(s["faculty"], 0) + 1

    print(f"Generated {len(students)} students -> {args.out}")
    print(f"  seed: {args.seed}")
    print("  faculty distribution:")
    for faculty, n in sorted(faculties.items(), key=lambda kv: -kv[1]):
        print(f"    {faculty:<18} {n}")


if __name__ == "__main__":
    main()
