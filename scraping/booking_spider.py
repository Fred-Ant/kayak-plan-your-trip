"""Spider Scrapy : collecte des hôtels de Booking.com pour les destinations du projet Kayak.

Les pages sont chargées par un vrai navigateur Chromium (extension scrapy-playwright), car Booking
protège ses pages par une vérification JavaScript (AWS WAF) qu'un client HTTP simple ne peut pas exécuter.
Aucun outil de camouflage n'est utilisé : le navigateur envoie ses propres en-têtes (User-Agent compris).

Exemples d'exécution (depuis la racine du projet, environnement "kayak" activé) :
    # Test sur une seule destination, navigateur visible, page HTML enregistrée pour analyse
    scrapy runspider scraping/booking_spider.py -a cities="Collioure" -a save_html=1 -O data/raw/booking_test.json

    # Toutes les destinations de data/raw/cities.csv (étape suivante)
    scrapy runspider scraping/booking_spider.py -O data/raw/hotels_booking.json
"""
import csv
import json
from pathlib import Path
from urllib.parse import urlencode

import scrapy
from scrapy_playwright.page import PageMethod

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://www.booking.com"
CARD_SELECTOR = 'div[data-testid="property-card"]'


class BookingSpider(scrapy.Spider):
    name = "booking"

    custom_settings = {
        # Téléchargement des pages par Playwright (navigateur réel) au lieu du client HTTP de Scrapy
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        # Le navigateur garde ses propres en-têtes : pas de User-Agent falsifié
        "PLAYWRIGHT_PROCESS_REQUEST_HEADERS": None,
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60_000,
        # Politesse : une page à la fois, pause entre deux pages
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 3,
        # robots.txt vérifié à la section 2 du notebook 03 : pages de recherche et d'hôtels autorisées
        "ROBOTSTXT_OBEY": False,
        "FEED_EXPORT_ENCODING": "utf-8",
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, cities: str | None = None, save_html: str = "0", headless: str = "0",
                 only_hotels: str = "1", **kwargs):
        """
        cities      : destinations séparées par des virgules ; par défaut, toutes celles de data/raw/cities.csv
        save_html   : "1" pour enregistrer le HTML rendu de chaque page de recherche dans data/raw/ (diagnostic)
        headless    : "1" pour un navigateur invisible ; "0" (défaut) pour voir ce que fait le navigateur
        only_hotels : "1" (défaut) pour ne garder que les hôtels (filtre Booking ht_id=204), "0" pour tous les hébergements
        """
        super().__init__(**kwargs)
        self.save_html = save_html == "1"
        self.only_hotels = only_hotels == "1"
        self.custom_launch_options = {"headless": headless == "1"}

        with open(RAW_DIR / "cities.csv", encoding="utf-8") as file:
            all_cities = {row["city_name"]: int(row["city_id"]) for row in csv.DictReader(file)}
        wanted = [name.strip() for name in cities.split(",")] if cities else list(all_cities)
        unknown = [name for name in wanted if name not in all_cities]
        if unknown:
            raise ValueError(f"Destinations absentes de cities.csv : {unknown}")
        self.targets = [(all_cities[name], name) for name in wanted]

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        # Option de lancement du navigateur (visible ou non) choisie à l'exécution
        crawler.settings.set("PLAYWRIGHT_LAUNCH_OPTIONS", spider.custom_launch_options, priority="spider")
        return spider

    async def start(self):
        for request in self.start_requests():
            yield request

    def start_requests(self):
        for city_id, city_name in self.targets:
            # Tri par note des clients pondérée par le nombre d'avis ; filtre facultatif "hôtels uniquement"
            params = {"ss": city_name, "lang": "fr", "order": "bayesian_review_score"}
            if self.only_hotels:
                params["nflt"] = "ht_id=204"
            yield scrapy.Request(
                f"{BASE_URL}/searchresults.fr.html?{urlencode(params)}",
                callback=self.parse_search,
                errback=self.on_error,
                meta={
                    "city_id": city_id,
                    "city_name": city_name,
                    "playwright": True,
                    "playwright_include_page": True,  # accès à la page pour diagnostic et fermeture
                    "playwright_page_methods": [
                        # Attendre l'affichage des fiches d'hôtels (après la vérification JavaScript)
                        PageMethod("wait_for_selector", CARD_SELECTOR, timeout=45_000),
                    ],
                },
            )

    async def parse_search(self, response):
        page = response.meta["playwright_page"]
        await page.close()

        city_name = response.meta["city_name"]
        if self.save_html:
            path = RAW_DIR / f"booking_search_{city_name.replace(' ', '_')}.html"
            path.write_text(response.text, encoding="utf-8")
            self.logger.info("HTML enregistré : %s", path)

        # Les données des établissements sont intégrées à la page dans un bloc JSON ("apollo"),
        # plus complet et plus stable que le HTML des fiches (coordonnées GPS, adresse, note, description...)
        results, total = [], None
        for block in response.xpath('//script[@data-capla-store-data="apollo"]/text()').getall():
            results, total = self.find_results(json.loads(block))
            if results:
                break

        nb_cards = len(response.css(CARD_SELECTOR))
        self.logger.info("%s : %d fiches affichées, %d établissements dans les données (sur %s au total)",
                         city_name, nb_cards, len(results), total)

        for position, result in enumerate(results, start=1):
            yield self.to_item(result, position, response.meta["city_id"], city_name)

    @classmethod
    def find_results(cls, node) -> tuple[list, int | None]:
        """Parcourt le JSON et renvoie la liste des résultats de recherche et le nombre total de résultats."""
        if isinstance(node, dict):
            results = node.get("results")
            if isinstance(results, list) and results and isinstance(results[0], dict) \
                    and results[0].get("__typename") == "SearchResultProperty":
                return results, (node.get("pagination") or {}).get("nbResultsTotal")
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            return [], None
        for child in children:
            found, total = cls.find_results(child)
            if found:
                return found, total
        return [], None

    @staticmethod
    def to_item(result: dict, position: int, city_id: int, city_name: str) -> dict:
        """Sélectionne les champs utiles d'un établissement (aucune donnée personnelle : ni avis, ni clients)."""
        data = result.get("basicPropertyData") or {}
        location = data.get("location") or {}
        reviews = data.get("reviews") or {}
        country = (location.get("countryCode") or "fr").lower()
        page_name = data.get("pageName")
        return {
            "city_id": city_id,
            "city_name": city_name,
            "search_position": position,
            "hotel_id": data.get("id"),
            "hotel_name": (result.get("displayName") or {}).get("text"),
            "hotel_url": f"{BASE_URL}/hotel/{country}/{page_name}.fr.html" if page_name else None,
            "accommodation_type_id": data.get("accommodationTypeId"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "address": location.get("address"),
            "hotel_city": location.get("city"),
            "distance_to_center": (result.get("location") or {}).get("mainDistance"),
            "review_score": reviews.get("totalScore") if reviews.get("showScore") else None,
            "review_count": reviews.get("reviewsCount"),
            "star_rating": (data.get("starRating") or {}).get("value"),
            "description": (result.get("description") or {}).get("text"),
        }

    async def on_error(self, failure):
        """En cas d'échec (vérification non passée, délai dépassé...), on enregistre la page pour comprendre."""
        meta = failure.request.meta
        page = meta.get("playwright_page")
        self.logger.error("Échec pour %s : %s", meta.get("city_name"), failure.getErrorMessage()[:200])
        if page:
            path = RAW_DIR / f"booking_error_{meta['city_name'].replace(' ', '_')}"
            (path.with_suffix(".html")).write_text(await page.content(), encoding="utf-8")
            await page.screenshot(path=str(path.with_suffix(".png")), full_page=True)
            await page.close()
            self.logger.error("Page d'erreur enregistrée : %s (.html et .png)", path)
