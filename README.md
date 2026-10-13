# EdgeGlass-AI 발표

Reveal.js 기반 16:9 발표 슬라이드입니다. 현재 1페이지만 구현되어 있습니다.

## 폴더 구조

```text
.
├── index.html                  # Reveal.js 슬라이드 마크업
├── css/
│   └── styles.css              # 전체 슬라이드 스타일
├── js/
│   └── presentation.js         # Reveal.js 설정
└── assets/
    └── images/
        └── concepts/           # 시안·참고 이미지
            └── smart-ar-glasses-prototype.png
```

앞으로 이미지는 목적별로 `assets/images/` 아래에 추가합니다. 예: 실제 촬영 사진은
`assets/images/photos/`, 아이콘은 `assets/images/icons/`에 보관합니다.

로컬 확인은 프로젝트 폴더에서 아래 명령을 실행한 뒤 브라우저로 표시된 주소를 여세요.

```sh
python3 -m http.server 8080
```

향후 슬라이드는 `index.html`의 `.slides` 안에 `<section>`을 추가해 확장합니다.
