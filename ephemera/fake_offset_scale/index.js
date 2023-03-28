#!/usr/bin/env node

const fs = require('fs');
const THREE = require('three.js-node');
const OBJLoader = require('three-obj-loader');
const { promisify } = require('util');
const sizeOf = promisify(require('image-size'));

// OBJLoader фигачит в stdout время загрузки, а нам это не нужно
console.log = function() {};

OBJLoader(THREE);

const program = require('commander');

program
    .version('0.0.1')
    .option('-m, --model <obj_file>', 'Путь до OBJ-файла с моделью.')
    .option(
        '-s, --meta [json_file]',
        'Путь до JSON-файла с метой. Если не задан, то ожидается в stdin.'
    )
    .option('-i, --image <minimap_file>', 'Путь до минимапы.')
    .parse(process.argv);

async function checkArgs() {
    let errors = [];
    if (program.model) {
        try {
            await fileExist(program.model);
        } catch (err) {
            const error = `Указанный файл ${program.model} модели не существует.`;
            errors.push(error);
        }
    } else {
        const error = 'Файл модели не задан.';
        errors.push(error);
    }
    if (program.meta) {
        try {
            await fileExist(program.meta);
        } catch (err) {
            const error = `Указанный файл ${program.meta} с метаданными не существует.`;
            errors.push(error);
        }
    }
    if (program.image) {
        try {
            await fileExist(program.image);
        } catch (err) {
            const error = `Указанная картинка ${program.image} не существует.`;
            errors.push(error);
        }
    }
    return errors.length > 0 ? Promise.reject(errors) : Promise.resolve();
}

async function fileExist(filePath) {
    return new Promise((resolve, reject) => {
        fs.access(filePath, fs.F_OK, err => {
            if (err) {
                return reject(false);
            }
            resolve(true);
        });
    });
}

function parseModel(path) {
    const rawModel = fs.readFileSync(path, 'utf8');
    const loader = new THREE.OBJLoader();
    return loader.parse(rawModel);
}

async function parseMeta(path) {
    if (path) {
        var rawMeta = fs.readFileSync(path, 'utf8');
        return Promise.resolve(JSON.parse(rawMeta));
    } else {
        return await readStdin();
    }
}

async function readStdin() {
    return new Promise((resolve, reject) => {
        const stdin = process.stdin;
        const inputChunks = [];

        stdin.resume();
        stdin.setEncoding('utf8');

        stdin.on('data', function(chunk) {
            inputChunks.push(chunk);
        });

        stdin.on('end', function() {
            const inputJSON = inputChunks.join('');
            resolve(JSON.parse(inputJSON));
        });
    });
}

function getSkyboxes(data) {
    const { skyboxes } = data;
    for (skyboxId in skyboxes) {
        const skybox = skyboxes[skyboxId];
        skybox.pos = new THREE.Vector3().fromArray(skybox.pos);
    }
    return skyboxes;
}

function getData(skyboxes, model, dimensions) {
    // 1. boundary box по скайбоксам с метровым запасом по бокам
    const { min: sbbMin, max: sbbMax, size: sbbSize } = getSbbParams(skyboxes);
    // console.log('sbb', sbbMin, sbbMax, sbbSize);
    // сколько метров в пикселе?
    const sbbScaleX = sbbSize.x / dimensions.width;
    const sbbScaleY = sbbSize.y / dimensions.height;
    // результирующий масштаб вписывания sbb в минимапу
    const sbbScale = Math.max(sbbScaleX, sbbScaleY);

    // 2. boundary box модели
    const { min: mbbMin, max: mbbMax, size: mbbSize } = getMbbParams(model);
    // console.log('mbb', mbbMin, mbbMax, mbbSize);
    // масштаб вписывания mbb в минимапу
    const mbbScale = mbbSize.x / dimensions.width;

    // 3. масштаб bb по скайбоксам к bb по модели
    const scale = sbbScale / mbbScale;

    // Вычисление смещения

    // левый нижний угол sbb в пикселях
    const f1 = new THREE.Vector2(0, 0);
    // смасштабированная точка
    const f2 = f1.clone().add(new THREE.Vector2(0, dimensions.height - sbbSize.y / sbbScale));
    // центрируем относительно центра минимапы
    const f3 = f2.clone().sub(new THREE.Vector2(dimensions.width / 2, dimensions.height / 2));

    // левый нижний угол sbb в метрах относительно mbb
    const p1 = sbbMin.clone().sub(mbbMin);
    // позиция в процентах
    const p2 = p1.clone().divide(mbbSize);
    // позиция в пикселях на минимапе
    const p3 = p2.clone().multiply(new THREE.Vector2(dimensions.width, dimensions.height));
    // позиция относительно центра
    const p4 = p3
        .clone()
        .sub(new THREE.Vector2(dimensions.width / 2, dimensions.height / 2))
        .divideScalar(scale);

    // итоговый offset
    const offset = p4.clone().sub(f3);
    const offsetRel = offset.clone().divide(new THREE.Vector2(dimensions.width, dimensions.height));

    return {
        scale: +(scale * 100).toFixed(2),
        offset: [+(offsetRel.x * 100).toFixed(2), +(offsetRel.y * -100).toFixed(2)]
    };
}

function getSbbParams(skyboxes) {
    const coords = Object.keys(skyboxes).map(id => skyboxes[id].pos);
    const box = new THREE.Box3().setFromPoints(coords);
    const min = box.min.clone().sub(new THREE.Vector3(1, 1, 0));
    const max = box.max.clone().add(new THREE.Vector3(1, 1, 0));
    const size = max.clone().sub(min);
    return {
        min: new THREE.Vector2(min.x, min.y),
        max: new THREE.Vector2(max.x, max.y),
        size: new THREE.Vector2(size.x, size.y)
    };
}

function getMbbParams(model) {
    const meshesWithoutFake = getNotFakeMeshes(model);
    const box = getBox3ByListObjects(meshesWithoutFake);
    const size = box.size();
    const { min, max } = box;
    return {
        min: new THREE.Vector2(min.x, min.y),
        max: new THREE.Vector2(max.x, max.y),
        size: new THREE.Vector2(size.x, size.y)
    };
}

function getNotFakeMeshes(model) {
    return model.children.filter(child => !child.name.match(/_fake/));
}

function getBox3ByListObjects(list) {
    var box = new THREE.Box3(),
        tmp = new THREE.Box3();
    list.forEach(function(el) {
        tmp.setFromObject(el);
        box.union(tmp);
    });
    return box;
}

async function main() {
    try {
        await checkArgs();
        // console.log(
        //     `Запущено вычисление смещения и масштаба с параметрами:\n* model path: ${
        //         program.model
        //     }\n* image path: ${program.image}`
        // );
        const model = parseModel(program.model);
        const meta = await parseMeta(program.meta);
        const skyboxes = getSkyboxes(meta);
        const scene = new THREE.Scene();
        scene.add(model);
        const dimensions = await sizeOf(program.image);
        const result = getData(skyboxes, model, dimensions);
        // console.log(JSON.stringify(result));
        process.stdout.write(JSON.stringify(result));
    } catch (err) {
        // console.error(err);
        process.stderr.write.write(err);
    }
}

main();
