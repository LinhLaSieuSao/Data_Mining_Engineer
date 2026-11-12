"""VietnamWorks IT crawler using the site's public job-search endpoint."""
import argparse
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from crawlers.base import make_record, clean_html, write_jsonl, export_csv, polite_delay

ENDPOINT = "https://ms.vietnamworks.com/job-search/v1.0/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
RETRIEVE_FIELDS = [
    "address", "benefits", "jobTitle", "salaryMax", "isSalaryVisible",
    "jobLevelVI", "salaryMin", "jobLevel", "jobId", "jobUrl", "alias",
    "workingLocations", "companyName", "salary", "skills", "jobDescription",
    "jobRequirement", "prettySalary", "createdOn", "approvedOn",
]


def request_body(page_number: int, keyword: str = "") -> dict:
    return {
        "userId": 0,
        "query": keyword,
        "filter": [{"field": "jobFunction", "value": '[{"parentId":5,"childrenIds":[-1]}]'}],
        "ranges": [], "order": [], "hitsPerPage": 50, "page": page_number,
        "retrieveFields": RETRIEVE_FIELDS,
        "summaryVersion": "", "variants": "test",
    }


def parse_job(job: dict) -> dict:
    url = job.get("jobUrl")
    if not url and job.get("alias") and job.get("jobId"):
        url = f"https://www.vietnamworks.com/{job['alias']}-{job['jobId']}-jv"
    locations = job.get("workingLocations") or []
    location_names = [
        item.get("cityNameVI") or item.get("address")
        for item in locations if isinstance(item, dict)
    ]
    skill_names = [
        item.get("skillName") for item in (job.get("skills") or [])
        if isinstance(item, dict) and item.get("skillName")
    ]
    description = clean_html(job.get("jobDescription"))
    requirements = clean_html(job.get("jobRequirement"))
    benefits = clean_html(job.get("benefits"))
    salary = job.get("prettySalary")
    if not salary and job.get("isSalaryVisible"):
        low, high = job.get("salaryMin"), job.get("salaryMax")
        salary = f"{low or ''} - {high or ''}".strip(" -") or None
    return make_record(
        "vietnamworks", url,
        title=job.get("jobTitle"),
        company=job.get("companyName"),
        location="; ".join(filter(None, location_names)) or job.get("address"),
        salary=salary,
        experience_level=job.get("jobLevelVI") or job.get("jobLevel"),
        posted_at=job.get("approvedOn") or job.get("createdOn"),
        skills=skill_names,
        description=description,
        requirements=requirements,
        benefits=benefits,
        raw_fields={
            "job_id": job.get("jobId"),
            "salary_min_original": job.get("salaryMin"),
            "salary_max_original": job.get("salaryMax"),
            "salary_visible": job.get("isSalaryVisible"),
            "working_locations": locations,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Crawl VietnamWorks IT jobs")
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--keyword", default="", help="Optional keyword, e.g. Data Engineer")
    parser.add_argument("--out", default="data/raw/vietnamworks.jsonl")
    parser.add_argument("--csv", default="data/raw/vietnamworks.csv")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # mỗi lần chạy tạo một bộ dữ liệu mới
    rows, seen = [], set()
    with sync_playwright() as playwright:
        request = playwright.request.new_context(
            user_agent=USER_AGENT,
            extra_http_headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=60000,
        )
        try:
            for number in range(args.pages):
                response = request.post(ENDPOINT, data=request_body(number, args.keyword))
                if not response.ok:
                    print(f"[WARN] API trả HTTP {response.status}; dừng.")
                    break
                payload = response.json()
                batch = [parse_job(job) for job in payload.get("data", [])]
                batch = [row for row in batch if row["job_url"] and row["job_url"] not in seen]
                if not batch:
                    break
                for row in batch:
                    seen.add(row["job_url"])
                if args.limit:
                    batch = batch[:max(0, args.limit - len(rows))]
                rows.extend(batch)
                write_jsonl(output, batch)
                print(f"Page {number + 1}: +{len(batch)}, tổng {len(rows)}")
                if args.limit and len(rows) >= args.limit:
                    break
                polite_delay()
        finally:
            request.dispose()
    count = export_csv(output, args.csv)
    print(f"Hoàn tất: {count} records | JSONL={output} | CSV={args.csv}")


if __name__ == "__main__":
    main()
