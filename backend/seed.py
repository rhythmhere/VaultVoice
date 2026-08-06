from sqlalchemy import select

from .db import Organization

ORGANIZATIONS = [
    {"name": "Legal Aid and Consultancy Centre", "categories": ["legal_aid", "harassment", "domestic_violence"], "districts": ["Kathmandu", "Lalitpur", "Bhaktapur"], "phone": "9841 333 333", "description": "Free legal information and referrals for women."},
    {"name": "Saathi", "categories": ["shelter", "domestic_violence", "legal_aid"], "districts": ["Kathmandu", "Lalitpur"], "phone": "01 555 4937", "description": "Counselling, shelter, and support for survivors."},
    {"name": "TPO Nepal", "categories": ["counselling", "harassment", "domestic_violence"], "districts": ["Kathmandu", "Lalitpur", "Bhaktapur"], "phone": "01 535 2807", "description": "Psychosocial counselling and community support."},
    {"name": "Women for Human Rights", "categories": ["shelter", "legal_aid"], "districts": ["Kathmandu"], "phone": "01 441 3526", "description": "Support and advocacy for survivors and single women."},
    {"name": "Nepal Bar Association Legal Aid", "categories": ["legal_aid"], "districts": ["Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara"], "phone": "01 420 0837", "description": "Legal referral and access to participating advocates."},
    {"name": "Maiti Nepal", "categories": ["shelter", "stalking", "domestic_violence"], "districts": ["Kathmandu"], "phone": "01 449 4816", "description": "Protection, rehabilitation, and crisis support."},
    {"name": "ABC Nepal", "categories": ["legal_aid", "domestic_violence", "harassment"], "districts": ["Kathmandu"], "phone": "01 449 2904", "description": "Advocacy, counselling, and legal support."},
    {"name": "OCCED Nepal", "categories": ["legal_aid", "workplace", "harassment"], "districts": ["Kathmandu"], "phone": "01 442 1412", "description": "Support and referrals for women and children."},
    {"name": "Kopila Nepal", "categories": ["shelter", "counselling", "domestic_violence"], "districts": ["Pokhara"], "phone": "061 465 353", "description": "Local counselling and protection services."},
    {"name": "WOREC Nepal", "categories": ["legal_aid", "harassment", "domestic_violence"], "districts": ["Kathmandu", "Lalitpur"], "phone": "01 515 5160", "description": "Women-led support, counselling, and referrals."},
]


def seed_organizations(session) -> None:
    if session.scalar(select(Organization.id).limit(1)):
        return
    session.add_all([Organization(name=item["name"], categories=item["categories"], districts=item["districts"], contact_phone=item["phone"], description=item["description"]) for item in ORGANIZATIONS])
    session.commit()
